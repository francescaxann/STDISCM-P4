import os
import grpc
import jwt
from flask import Flask, render_template, request, redirect, url_for, make_response, flash
import enrollment_pb2
import enrollment_pb2_grpc

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "demo-flash-secret")
app.config["SESSION_COOKIE_NAME"] = "flask_session"
PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "/app/view-node/public.pem")
AUTH = os.getenv("AUTH_HOST", "auth-node") + ":50051"
COURSE = os.getenv("COURSE_HOST", "course-node") + ":50052"
GRADE = os.getenv("GRADE_HOST", "grade-node") + ":50053"
AUDIT = os.getenv("AUDIT_HOST", "audit-node") + ":50054"
CHANNEL_OPTIONS = (("grpc.max_reconnect_backoff_ms", 1000),)
auth_channel = grpc.insecure_channel(AUTH, options=CHANNEL_OPTIONS)
course_channel = grpc.insecure_channel(COURSE, options=CHANNEL_OPTIONS)
grade_channel = grpc.insecure_channel(GRADE, options=CHANNEL_OPTIONS)
audit_channel = grpc.insecure_channel(AUDIT, options=CHANNEL_OPTIONS)
auth_stub = enrollment_pb2_grpc.AuthServiceStub(auth_channel)
course_stub = enrollment_pb2_grpc.CourseServiceStub(course_channel)
grade_stub = enrollment_pb2_grpc.GradeServiceStub(grade_channel)
audit_stub = enrollment_pb2_grpc.AuditServiceStub(audit_channel)


def public_key():
    with open(PUBLIC_KEY, "rb") as fh:
        return fh.read()


def claims():
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        result = auth_stub.ValidateToken(
            enrollment_pb2.ValidateRequest(token=token), timeout=2.0)
        if result.valid:
            return {"sub": result.user_id, "role": result.role}
        return None
    except grpc.RpcError as exc:
        if exc.code() not in (grpc.StatusCode.UNAVAILABLE,
                              grpc.StatusCode.DEADLINE_EXCEEDED):
            return None
        try:
            return jwt.decode(token, public_key(), algorithms=["RS256"])
        except jwt.PyJWTError:
            return None


def metadata():
    token = request.cookies.get("session", "")
    return (("authorization", f"Bearer {token}"),)


def grpc_call(call, *, retry=False, timeout=2.0):
    retryable = (grpc.StatusCode.UNAVAILABLE,
                 grpc.StatusCode.DEADLINE_EXCEEDED,
                 grpc.StatusCode.UNKNOWN)
    last_error = None
    for attempt in range(2 if retry else 1):
        try:
            return call(), None
        except grpc.RpcError as exc:
            last_error = exc
            if not retry or exc.code() not in retryable:
                break
    return None, last_error


@app.context_processor
def nav():
    return {"claims": claims()}


@app.route("/")
def index():
    c = claims()
    return render_template("dashboard.html", claims=c) if c else redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        def call():
            return auth_stub.Login(enrollment_pb2.LoginRequest(
                username=request.form.get("username", ""),
                password=request.form.get("password", "")), timeout=2.0)
        res, error = grpc_call(call)
        if error:
            flash("Authentication service unavailable")
            return render_template("login.html"), 503
        if not res or not res.success:
            flash(res.message if res else "Invalid credentials")
            return redirect(url_for("login"))
        response = make_response(redirect(url_for("index")))
        response.set_cookie("session", res.token, httponly=True, secure=True, samesite="Lax")
        return response
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get("session", "")
    if token:
        try:
            auth_stub.Logout(enrollment_pb2.LogoutRequest(token=token), timeout=2.0)
        except grpc.RpcError:
            pass
    response = make_response(redirect(url_for("login")))
    response.delete_cookie("session")
    flash("Logged out")
    return response


@app.route("/courses")
def courses():
    c = claims()
    if not c:
        return redirect(url_for("login"))
    def call():
        return course_stub.GetOpenCourses(enrollment_pb2.CoursesRequest(), timeout=2.0,
                                          metadata=metadata())
    res, error = grpc_call(call, retry=True)
    return render_template("courses.html", courses=res.courses if res else [],
                           warning="Unavailable" if error else None, claims=c)


@app.route("/courses/enroll", methods=["POST"])
def enroll():
    c = claims()
    if not c:
        return redirect(url_for("login"))
    raw = request.form.get("course_id", "")
    if not raw.isdigit():
        flash("A valid course ID is required")
        return redirect(url_for("courses"), code=303)
    def call():
        return course_stub.EnrollStudent(enrollment_pb2.EnrollRequest(course_id=int(raw)),
                                         timeout=2.0, metadata=metadata())
    res, error = grpc_call(call)
    flash(res.message if res else "Course service unavailable")
    return redirect(url_for("courses"), code=303)


@app.route("/grades")
def grades():
    c = claims()
    if not c:
        return redirect(url_for("login"))
    def call():
        return grade_stub.GetStudentGrades(enrollment_pb2.GradesRequest(), timeout=2.0,
                                           metadata=metadata())
    res, error = grpc_call(call, retry=True)
    students = [{"id": "11111111-1111-1111-1111-111111111111", "name": "student"}]
    return render_template("grades.html", grades=res.grades if res else [],
                           warning="Unavailable" if error else None, claims=c,
                           students=students)


@app.route("/grades/upload", methods=["POST"])
def upload_grade():
    c = claims()
    if not c or c["role"] != "FACULTY":
        return redirect(url_for("login"))
    raw_course = request.form.get("course_id", "")
    if not raw_course.isdigit():
        flash("A valid course ID is required")
        return redirect(url_for("grades"), code=303)
    def call():
        return grade_stub.UploadGrade(enrollment_pb2.UploadGradeRequest(
            student_id=request.form.get("student_id", ""),
            course_id=int(raw_course), grade=request.form.get("grade", "")),
            timeout=2.0, metadata=metadata())
    res, error = grpc_call(call)
    flash(res.message if res else "Grade service unavailable")
    return redirect(url_for("grades"), code=303)


@app.route("/receipts")
def receipts():
    c = claims()
    if not c:
        return redirect(url_for("login"))
    try:
        res = audit_stub.ListReceipts(enrollment_pb2.ReceiptFilter(student_id=c["sub"]),
                                      timeout=2.0, metadata=metadata())
    except grpc.RpcError:
        return render_template("receipts.html", receipts=[], warning="Unavailable", claims=c)
    return render_template("receipts.html", receipts=res.receipts, warning=None, claims=c)


@app.route("/receipts", methods=["POST"])
def create_receipt():
    c = claims()
    if not c:
        return redirect(url_for("login"))
    raw_course = request.form.get("course_id", "")
    if not raw_course.isdigit():
        flash("A valid course ID is required")
        return redirect(url_for("receipts"), code=303)
    try:
        res = audit_stub.CreateReceipt(enrollment_pb2.Receipt(
            student_id=c["sub"], course_id=int(raw_course),
            status=request.form.get("status", "CREATED"),
            details=request.form.get("details", "")), timeout=2.0, metadata=metadata())
        flash(res.message)
    except grpc.RpcError:
        flash("Receipt service unavailable")
    return redirect(url_for("receipts"), code=303)


@app.route("/receipts/<int:receipt_id>/update", methods=["POST"])
def update_receipt(receipt_id):
    c = claims()
    if not c:
        return redirect(url_for("login"))
    try:
        res = audit_stub.UpdateReceipt(enrollment_pb2.Receipt(
            id=receipt_id, status=request.form.get("status", "UPDATED"),
            details=request.form.get("details", "")), timeout=2.0, metadata=metadata())
        flash(res.message)
    except grpc.RpcError:
        flash("Receipt service unavailable")
    return redirect(url_for("receipts"), code=303)


@app.route("/receipts/<int:receipt_id>/delete", methods=["POST"])
def delete_receipt(receipt_id):
    c = claims()
    if not c:
        return redirect(url_for("login"))
    try:
        res = audit_stub.DeleteReceipt(enrollment_pb2.ReceiptKey(id=receipt_id),
                                       timeout=2.0, metadata=metadata())
        flash(res.message)
    except grpc.RpcError:
        flash("Receipt service unavailable")
    return redirect(url_for("receipts"), code=303)


if __name__ == "__main__":
    cert = os.getenv("TLS_CERT", "view-node/certs/server.crt")
    key = os.getenv("TLS_KEY", "view-node/certs/server.key")
    app.run(host="0.0.0.0", port=8080, ssl_context=(cert, key))
