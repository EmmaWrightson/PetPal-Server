from fastapi import FastAPI, Request, Form, Query,status, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, RedirectResponse
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles   # Used for serving static files
import uvicorn
import os
import base64
from pydantic import BaseModel, EmailStr
import json
from typing import Optional
import mysql.connector as mysql
from dotenv import load_dotenv
import datetime
import uuid
from typing import Dict
from contextlib import asynccontextmanager
import hashlib
from datetime import datetime, timedelta
import asyncio
import requests
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

SYSTEM_SALT = b"my-fixed-salt-12345"
motor_queue = []
audio_out_queue = []


#change number value for different time-out time in minutes
SESSION_TIMEOUT = timedelta(minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", 5)))



class SensorType(BaseModel):
    value: float
    unit: str
    timestamp: Optional[str] = None

class SensorValues(BaseModel):
    temp: float
    timestamp: str
    topic: str

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    location: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class MotorCommand(BaseModel):
    motor: int

from app.database import (
    getTables,
    connectdb,
    setup_database,
    get_user_by_email,
    get_user_by_name,
    get_user_by_id,
    create_session,
    get_session,
    delete_session,
)

@asynccontextmanager
async def setup(app: FastAPI):
    """
    Lifespan context manager for managing application startup and shutdown.
    Handles database setup and cleanup in a more structured way.
    """
    # Startup: Setup resources
    print("In Setup...")
    try:
        # Make sure setup_database is async
        await setup_database()
        print("Database setup completed")
        yield
    finally:
        print("Shutdown completed")
 

app = FastAPI(lifespan=setup)
static_files = StaticFiles(directory='app/public')
app.mount('/public', static_files, name='public')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#Update last time user was active, store in session database
async def update_last_active(session_id: str):
    cursor, db = connectdb()
    cursor.execute("UPDATE sessions SET last_active = %s WHERE id = %s", (datetime.now(), session_id))
    db.commit()
    db.close()

#if session expires
async def is_session_expired(session: dict) -> bool:
    return datetime.now() > session["last_active"] + SESSION_TIMEOUT


async def validate_session(request: Request):
    sessionId = request.cookies.get("session_id")
    if not sessionId:
        return RedirectResponse(url="/login")  # Redirect if no session ID

    session = await get_session(sessionId)

    if not session:
        return RedirectResponse(url="/login")  # Redirect if invalid session

    if await is_session_expired(session):
        await delete_session(sessionId)
        return RedirectResponse(url="/login")  # Redirect if session expired

    await update_last_active(sessionId) #update session active time

    return session

#delete sessions that have expired
async def cleanup_expired_sessions():
    while True:
        cursor, db = connectdb()
        cursor.execute("DELETE FROM sessions WHERE last_active < %s", (datetime.now() - SESSION_TIMEOUT,))
        db.commit()
        db.close()
        await asyncio.sleep(600)

#delete all sessions that are still open but expired, on start up
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    cookies = websocket.cookies
    sessionid = cookies.get("session_id")
    if sessionid:
        session = await get_session(sessionid) #get session from sessionID
        if session:
            user_id = session['user_id']
            if user_id:
                try:
                    while True:
                        cursor, db = connectdb()
                        cursor2 = db.cursor()
                        cursor2.execute("SELECT topic, temperature, timestamp FROM sensor_temp WHERE user_id = %s", (user_id,))
                        result = cursor2.fetchall()
                        data = []
                        for row in result:
                            data.append({
                            "topic": row[0],
                            "temperature": row[1],
                            "timestamp": row[2].strftime('%Y-%m-%d %H:%M:%S')  # Format timestamp if needed
                            })
                        await websocket.send_json(data)
                        await asyncio.sleep(5)
                except Exception as e:
                    print(f"Something went wrong: {e}")
                finally:
                    cursor.close()
                    await websocket.close()
            
    else:
        await websocket.send_text("Error: user_id cookie not found")
        await websocket.close()
        return


# Static file helpers
def read_html(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()

def get_error_html(name: str) -> str:
    error_html = read_html("app/public/error.html")
    return error_html.replace("{name}", name)

def get_error_email(email: str) -> str:
    error_html = read_html("app/public/error_email.html")
    return error_html.replace("{email}", email)


#main page route
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def get_html() -> HTMLResponse:
    with open("app/public/index.html") as html:
        return HTMLResponse(content=html.read())


@app.post("/api/motor")
async def send_motor_command(cmd: MotorCommand):
    motor_queue.append(cmd.motor)
    return {"message": f"Motor {cmd.motor} command received"}

@app.post("/api/sound")
async def send_audio_command(audio_base64: str):
    audio_out_queue.append(audio_base64)
    return {"status": "queued"}


@app.websocket("/ws/motor")
async def motor_ws(websocket: WebSocket):
    await websocket.accept()
    while True:
        if motor_queue:
            motor = motor_queue.pop(0)
            await websocket.send_json({"motor": motor})
        await asyncio.sleep(1) 


@app.websocket("/ws/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            msg = await websocket.recieve_text()
            data = json.loads(msg)

            if data["type"] == "video":
                video_data = base64.b64decode(data["data"])
                with open("frame.jpg", "wb") as f:
                    f.write(video_data)

            elif data["type"] == "audio":
                audio_data = base64.b64decode(data["data"])
                with open("audio_chunk.wav", "wb") as f:
                    f.write(audio_data)

            if motor_queue:
                motor = motor_queue.pop(0)
                await websocket.send_json({
                    "type": "command", 
                    "motor": motor
                })

            if audio_out_queue:
                audio_data = audio_out_queue.pop(0)
                await websocket.send_json({
                    "type": "audio_out",
                    "data": audio_data
                })


            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print("Client disconnected")


@app.get("/feed", response_class=HTMLResponse)
async def live_page(request : Request):
    return HTMLResponse(read_html("app/public/feed.html"))

@app.get("/dispense", response_class=HTMLResponse)
async def dispense_page(request: Request):
    return HTMLResponse(read_html("app/public/dispense.html"))





#login page routes 
@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Show login if not logged in, or redirect to profile page"""
    #check if a sessionId is attached to cookies and validate
    sessionid = request.cookies.get("session_id")
    if sessionid:
        session = await get_session(sessionid) #get session from sessionID
        if session:
            user = await get_user_by_id(session['user_id']) #get user from session 
            if user: #if valid go to profile
                return RedirectResponse(url=f"/user/{user['name']}")
    return HTMLResponse(read_html("app/public/login.html"))


@app.post("/login")
async def login(request: Request):
    """Validate credentials and create a new session if valid"""
    #get email and password from form data
    form = await request.form() 
    email = form.get("email")
    password = form.get("password")

    if not email or not password:
        return HTMLResponse(read_html("app/public/login.html"))

    hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode(), SYSTEM_SALT, 100000)
    password = hashed_password.hex()
    
    #check if email exists and password matches
    user = await get_user_by_email(email)
    if not user or user['password'] != password:
        return HTMLResponse(get_error_email(email), status_code=403)

    #creating new session
    sessionId = str(uuid.uuid4())
    await create_session(user['id'], sessionId)

    #response = redirect + cookie
    response = RedirectResponse(url=f"/user/{user['name']}", status_code = 302)
    response.set_cookie("session_id", sessionId)
    return response
 

#signup page routes (basic get html for now)
@app.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def get_html(request:Request) -> HTMLResponse:
    sessionid = request.cookies.get("session_id")
    if sessionid:
        session = await get_session(sessionid) #get session from sessionID
        if session:
            user = await get_user_by_id(session['user_id']) #get user from session 
            if user: #if valid go to profile
                return RedirectResponse(url=f"/user/{user['name']}")
    with open("app/public/signup.html") as html:
        return HTMLResponse(content=html.read())



@app.post("/signup")
async def signup(request: Request):
    #get form inputs
    form = await request.form() 
    name = form.get("name")
    email = form.get("email")
    password = form.get("password")

    hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode(), SYSTEM_SALT, 100000)
    password = hashed_password.hex()

    location = form.get("location")

    #check if the user already exists
    existing_user = await get_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    #else - > insert the new user into the database
    cursor, db = connectdb()
    try:
        cursor.execute(
            "INSERT INTO users (name, email, password, location) VALUES (%s, %s, %s, %s)",
            (name, email, password, location)
        )
        #save to database
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        db.close()
    #go to login page after to login as a user
    return HTMLResponse(read_html("app/public/login.html")) 

@app.post("/api/signup", status_code=201)
async def api_signup(payload: SignupRequest):
    existing = await get_user_by_email(payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )
    
    hashed = hashlib.pbkdf2_hmac("sha256", payload.password.encode(), SYSTEM_SALT, 100000)
    password = hashed.hex()

    cursor, db = connectdb()
    try:
        cursor.execute(
            """
            INSERT INTO users (name, email, password, location)
            VALUES (%s, %s, %s, %s)
            """, (payload.name, payload.email, password, payload.location),
        )
        db.commit()
        new_id = cursor.lastrowid
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail = "Database error")
    finally:
        db.close()

    return {"id": new_id, "name": payload.name, "email": payload.email}

@app.post("/api/login", status_code=status.HTTP_200_OK)
async def api_login(payload: LoginRequest, response: Response):
    hashed_password = hashlib.pbkdf2_hmac("sha256", payload.password.encode(), SYSTEM_SALT, 100000)
    password = hashed_password.hex()

    user = await get_user_by_email(payload.email)
    if not user or user["password"] != password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    
    session_id = str(uuid.uuid4())
    await create_session(user["id"], session_id)

    response.set_cookie("session_id", session_id)

    return {"id":user["id"], "name":user["name"], "email": user["email"]}

#user hub page route
@app.get("/user/{name}", response_class=HTMLResponse)
async def user_page(name: str, request: Request):
    session_result = await validate_session(request)
    if isinstance(session_result, RedirectResponse):
        return session_result
    user = await get_user_by_id(session_result['user_id'])
    if not user or user['name'] != name:
        return HTMLResponse(get_error_html(name), status_code = 403)

    #If all valid, show profile page
    return HTMLResponse(read_html("app/public/profile.html"))



#profile page routes (basic get html for now)
@app.get("/profile", response_class=HTMLResponse, include_in_schema=False)
async def get_html(request:Request) -> HTMLResponse:
    session_result = await validate_session(request)
    if isinstance(session_result, RedirectResponse):
        return session_result
    with open("app/public/profile_devices.html") as html:
        return HTMLResponse(content=html.read())

#logout route


@app.post("/logout")
async def logout(request: Request):
    """Clear session and redirect to login page"""
    #Create redirect response to /login
    sessionId = request.cookies.get('session_id')
    response = RedirectResponse(url="/login")
    #Delete sessionId cookie, and delete sessionId from database
    if sessionId:
        await delete_session(sessionId)
    response.delete_cookie("sessionId")
    #Return response
    return response


getTables()



if __name__ == "__main__":
   uvicorn.run(app="app.main:app", host="0.0.0.0", port=6543, reload=True)
   