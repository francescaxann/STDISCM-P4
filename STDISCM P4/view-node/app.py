import os
import grpc
import jwt
from flask import Flask, render_template, request, redirect, url_for, make_response
import enrollment_pb2, enrollment_pb2_grpc

app=Flask(__name__)
SECRET=os.getenv('JWT_SECRET','dev-enrollment-secret')
AUTH=os.getenv('AUTH_HOST','auth-node')+':50051'
COURSE=os.getenv('COURSE_HOST','course-node')+':50052'
GRADE=os.getenv('GRADE_HOST','grade-node')+':50053'

def claims():
    token=request.cookies.get('session')
    if not token: return None
    try: return jwt.decode(token,SECRET,algorithms=['HS256'])
    except jwt.PyJWTError: return None

def grpc_call(call, *, retry=False, timeout=2.0):
    attempts = 2 if retry else 1
    last_error = None
    for attempt in range(attempts):
        try:
            return call(), None
        except grpc.RpcError as exc:
            last_error = exc
            code = exc.code()
            if not retry or code not in (grpc.StatusCode.UNAVAILABLE,
                                          grpc.StatusCode.DEADLINE_EXCEEDED):
                break
    return None, last_error


def service_warning(error):
    return 'Unavailable' if error is not None else None

@app.context_processor
def nav(): return {'claims':claims()}

@app.route('/')
def index():
    c=claims()
    return render_template('dashboard.html',claims=c) if c else redirect(url_for('login'))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        chan=grpc.insecure_channel(AUTH)
        stub=enrollment_pb2_grpc.AuthServiceStub(chan)
        try:
            res=stub.Login(enrollment_pb2.LoginRequest(username=request.form['username'],password=request.form['password']),timeout=2.0)
        except grpc.RpcError:
            return render_template('login.html',error='Authentication service unavailable')
        if res.success:
            response=make_response(redirect(url_for('index')))
            response.set_cookie('session',res.token,httponly=True,samesite='Lax')
            return response
        return render_template('login.html',error=res.message)
    return render_template('login.html')

@app.route('/logout',methods=['POST'])
def logout():
    token=request.cookies.get('session','')
    if token:
        def call():
            stub=enrollment_pb2_grpc.AuthServiceStub(grpc.insecure_channel(AUTH))
            return stub.Logout(enrollment_pb2.LogoutRequest(token=token),timeout=2.0)
        grpc_call(call,retry=False)
    response=make_response(redirect(url_for('login')))
    response.delete_cookie('session')
    return response

@app.route('/courses')
def courses():
    c=claims()
    if not c: return redirect(url_for('login'))
    chan=grpc.insecure_channel(COURSE)
    stub=enrollment_pb2_grpc.CourseServiceStub(chan)
    def call():
        return stub.GetOpenCourses(enrollment_pb2.CoursesRequest(user_id=c['sub'],role=c['role']),timeout=2.0)
    res,error=grpc_call(call,retry=True)
    warning=service_warning(error)
    return render_template('courses.html',courses=res.courses if res else [],warning=warning,claims=c)

@app.route('/courses/<int:course_id>/enroll',methods=['POST'])
def enroll(course_id):
    c=claims()
    if not c: return redirect(url_for('login'))
    chan=grpc.insecure_channel(COURSE)
    stub=enrollment_pb2_grpc.CourseServiceStub(chan)
    def call():
        return stub.EnrollStudent(enrollment_pb2.EnrollRequest(user_id=c['sub'],role=c['role'],course_id=course_id),timeout=2.0)
    res,error=grpc_call(call,retry=False)
    message=res.message if res else ('Course service unavailable' if error else 'Enrollment could not be completed')
    return render_template('courses.html',courses=[],warning=None,message=message,claims=c)

@app.route('/grades')
def grades():
    c=claims()
    if not c: return redirect(url_for('login'))
    chan=grpc.insecure_channel(GRADE)
    stub=enrollment_pb2_grpc.GradeServiceStub(chan)
    def call():
        return stub.GetStudentGrades(enrollment_pb2.GradesRequest(user_id=c['sub'],role=c['role']),timeout=2.0)
    res,error=grpc_call(call,retry=True)
    warning=service_warning(error)
    return render_template('grades.html',grades=res.grades if res else [],warning=warning,claims=c)

@app.route('/grades/upload',methods=['POST'])
def upload_grade():
    c=claims()
    if not c or c['role']!='FACULTY': return redirect(url_for('login'))
    stub=enrollment_pb2_grpc.GradeServiceStub(grpc.insecure_channel(GRADE))
    def call():
        return stub.UploadGrade(enrollment_pb2.UploadGradeRequest(user_id=c['sub'],role=c['role'],student_id=request.form['student_id'],course_id=int(request.form['course_id']),grade=request.form['grade']),timeout=2.0)
    res,error=grpc_call(call,retry=False)
    message=res.message if res else ('Grade service unavailable' if error else 'Grade could not be saved')
    return render_template('grades.html',grades=[],warning=None,message=message,claims=c)

if __name__=='__main__': app.run(host='0.0.0.0',port=8080)
