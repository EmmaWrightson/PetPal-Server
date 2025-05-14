from fastapi import FastAPI, Request, Form, Query,status, HTTPException, Body, WebSocket
from fastapi.responses import Response, RedirectResponse
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles   # Used for serving static files
import uvicorn
import os
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


load_dotenv()

SYSTEM_SALT = b"my-fixed-salt-12345"

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

# #profile stuff
# @app.get("/profile/devices", response_class=JSONResponse)
# async def get_wardrobe_items(request: Request):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()
#     cursor, db = connectdb()
#     cursor.execute("SELECT id, device_topic FROM user_devices WHERE user_id = %s", (user_id,))
#     items = cursor.fetchall()
#     db.close()

#     return {"items": items}

# @app.post("/profile")
# async def register_device(request: Request, data: dict = Body(...)):
#     # Get sessionId from cookies
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']


#     cursor, db = connectdb()
#     try:
#         cursor.execute(
#             "INSERT INTO user_devices (user_id, device_topic) VALUES (%s, %s)",
#             (user_id, data["device_topic"])
#         )
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Item created successfully"}

# @app.put("/profile/{device_id}")
# async def update_item(request: Request, device_id: int, data: dict = Body(...)):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()
#     cursor.execute("SELECT * FROM user_devices WHERE id = %s AND user_id = %s", (device_id, user_id))
#     item = cursor.fetchone()

#     if not item:
#         db.close()
#         raise HTTPException(status_code=404, detail="Item not found")

#     try:
#         cursor.execute("UPDATE user_devices SET device_topic = %s WHERE id = %s", (data["device_topic"], device_id))
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Device updated successfully"}


# @app.delete("/profile/{device_id}")
# async def delete_item(request: Request, device_id: int):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()
#     cursor.execute("SELECT device_topic FROM user_devices WHERE id = %s AND user_id = %s", (device_id, user_id))
#     item = cursor.fetchone()


#     if not item:
#         db.close()
#         raise HTTPException(status_code=404, detail="Item not found")

#     my_topic = item["device_topic"]

#     try:
#         cursor.execute("DELETE FROM user_devices WHERE id = %s", (device_id,))
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
        
#     cursor.execute("SELECT * FROM sensor_temp WHERE topic = %s", (my_topic,))
#     item2 = cursor.fetchall()

#     if not item2:
#         db.close()
#         raise HTTPException(status_code=404, detail="Item not found")

#     try:
#         cursor.execute("DELETE FROM sensor_temp WHERE topic = %s", (my_topic,))
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Device deleted successfully"}



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


# Dashboard route
# @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
# async def get_dashboard(request : Request) -> HTMLResponse:
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     with open("app/public/dashboard.html") as html:
#         return HTMLResponse(content=html.read())

# #get location from user database
# @app.get("/dashboard/location")
# async def get_user_location(request: Request):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     try:
#         #query the database to get the user's location
#         cursor, db = connectdb()
#         cursor.execute("SELECT location FROM users WHERE id = %s", (user_id,))
#         result = cursor.fetchall()
#         db.close()

#         if not result:
#             raise HTTPException(status_code=404, detail="Location not found")

#         location = result[0]['location']
    
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

#     #return location of user to use for weatherapi
#     return {"location": location}



# @app.get("/wardrobe/items", response_class=JSONResponse)
# async def get_wardrobe_items(request: Request):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']
#     cursor, db = connectdb()
#     cursor.execute("SELECT id, clothes FROM wardrobe WHERE user_id = %s", (user_id,))
#     items = cursor.fetchall()
#     db.close()

#     return {"items": items}


# @app.get("/wardrobe", response_class=HTMLResponse)
# async def get_wardrobe(request: Request) -> HTMLResponse:
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     with open("app/public/wardrobe.html") as html:
#         return HTMLResponse(content=html.read())
    

# @app.post("/wardrobe")
# async def create_item(request: Request, data: dict = Body(...)):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()

#     try:
#         cursor.execute(
#             "INSERT INTO wardrobe (user_id, clothes) VALUES (%s, %s)",
#             (user_id, data["clothes"])
#         )
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Item created successfully"}


# @app.put("/wardrobe/{item_id}")
# async def update_item(request: Request, item_id: int, data: dict = Body(...)):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()
#     cursor.execute("SELECT * FROM wardrobe WHERE id = %s AND user_id = %s", (item_id, user_id))
#     item = cursor.fetchone()

#     if not item:
#         db.close()
#         raise HTTPException(status_code=404, detail="Item not found")

#     try:
#         cursor.execute("UPDATE wardrobe SET clothes = %s WHERE id = %s", (data["clothes"], item_id))
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Item updated successfully"}


# @app.delete("/wardrobe/{item_id}")
# async def delete_item(request: Request, item_id: int):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']

#     cursor, db = connectdb()
#     cursor.execute("SELECT * FROM wardrobe WHERE id = %s AND user_id = %s", (item_id, user_id))
#     item = cursor.fetchone()

#     if not item:
#         db.close()
#         raise HTTPException(status_code=404, detail="Item not found")

#     try:
#         cursor.execute("DELETE FROM wardrobe WHERE id = %s", (item_id,))
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="Database error")
#     finally:
#         db.close()

#     return {"message": "Item deleted successfully"}





# @app.get("/api/{sensor_type}", response_class=JSONResponse)
# def get_sensor_type(sensor_type:str, 
#                     order_by:str=Query(None, alias="order-by"), 
#                     start_date:str=Query(None, alias="start-date"), 
#                     end_date:str=Query(None, alias="end-date")) -> JSONResponse:
    
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")

#     cursor, db = connectdb()

#     query = f"SELECT * FROM {sensor_type}"

#     if start_date and end_date:
#         query += f" WHERE timestamp >= '{start_date}' AND timestamp <= '{end_date}'"
#     elif end_date:
#         query += f" WHERE timestamp <= '{end_date}'"
#     elif start_date:
#         query += f" WHERE timestamp >= '{start_date}'"

#     if order_by:
#         if order_by in {"timestamp", "value"}:
#             query += f" ORDER BY {order_by}"
#         else:
#             raise HTTPException(status_code=404, detail="Invalid order")

#     #print("DEBUG: ****************************", query)
#     cursor.execute(query)
#     results = cursor.fetchall()
#     for result in results:
#         result['timestamp'] = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
#     db.close()

#     if not results:
#         raise HTTPException(status_code=404, detail="No data found")

#     return JSONResponse(content=results)
    

# @app.get("/api/{sensor_type}/count")
# def get_count(sensor_type:str) -> int:
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")
#     cursor, db = connectdb()
#     cursori = db.cursor()
#     cursori.execute(f"select count(*) from {sensor_type}")
#     count = cursori.fetchone()[0]
#     db.close()
#     return count

# @app.post("/sensor_data")
# async def update_temps(request: SensorValues) -> dict:
#     cursor, db = connectdb()
#     cursor2 = db.cursor()
#     topic = request.topic
#     topic = topic.split('/')[0]
#     #print(topic)
#     temp = request.temp
#     time = request.timestamp

#     #print(temp)
#     #print(time)
#     try:
#         cursor2.execute("SELECT * FROM user_devices WHERE device_topic = %s", (topic,))
#         user = cursor2.fetchone()

#         #print(user)
#         if user:
#             cursor2.execute("""
#             insert into sensor_temp (user_id, topic, temperature, timestamp) 
#             values (%s, %s, %s, %s)
#             """, (user[1], topic, temp, time))


#             db.commit()
#             id = cursor2.lastrowid
#             db.close()
#             return {"id": id}
#     except:
#         db.close()
#         return {"id" : -1}
#     finally:
#         db.close()
#         return {"id" : -1}


    

# @app.post("/api/{sensor_type}")
# def post_sensor_type(sensor_type:str, request:SensorType) -> dict:
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")
#     cursor, db = connectdb()
#     cursor2 = db.cursor()

#     timestamp = request.timestamp if request.timestamp else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     value = request.value
#     unit = request.unit
#     cursor2.execute(f"""insert into {sensor_type} (timestamp, value, unit) 
#                     values (%s, %s, %s)""", (timestamp, value, unit))
#     db.commit()
#     id = cursor2.lastrowid
#     db.close()
#     return {'id':id}



# @app.get("/api/{sensor_type}/{id}")
# def get_id_data(sensor_type:str, id:int) -> dict:
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")
#     cursor, db = connectdb()
#     if id == None:
#         cursor.execute(f"select * from {sensor_type};")
#         result = cursor.fetchall()
#     else:
#         cursor.execute(f"select * from {sensor_type} where id={id};")
#         result = cursor.fetchone()
#         if (not result):
#             db.close()
#             raise HTTPException(status_code=404, detail="ID not found")
#     db.close()
#     return result


# @app.put("/api/{sensor_type}/{id}")
# async def update_data(sensor_type:str, id:int, request:SensorType) -> dict:
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")
#     cursor, db = connectdb()
#     cursor2 = db.cursor()

#     queryList = []
#     params = []
    
#     if request.value is not None:
#         queryList.append("value = %s")
#         params.append(request.value)
#     if request.unit is not None:
#         queryList.append("unit = %s")
#         params.append(request.unit)
#     if request.timestamp is not None:
#         queryList.append("timestamp = %s")
#         params.append(request.timestamp)
#     if not queryList:
#         raise HTTPException(status_code=404, detail="No Valid Input")

#     params.append(id)
#     query = f"update {sensor_type} set {', '.join(queryList)} where id = %s"
#     cursor2.execute(query, params)
#     db.commit()
#     db.close()

#     return {"message": "Database updated successfully"}

# @app.delete("/api/{sensor_type}/{id}")
# def delete_data(sensor_type:str, id:int) -> dict:
#     valid_tables = {"humidity", "light", "temperature"}
#     if sensor_type not in valid_tables:
#         raise HTTPException(status_code=404, detail="Sensor type not found")
#     cursor, db = connectdb()
#     cursor2 = db.cursor()
#     cursor2.execute(f"delete from {sensor_type} where id={id}")
#     db.commit()
#     db.close()
#     return {"message": "Data row deleted successfully"}


# EMAIL = os.getenv("EMAIL")
# PID = os.getenv("PID")

# class weatherClass(BaseModel):
#     temp: str
#     cond: str

# @app.post("/get_suggestion")
# async def get_recommended(data : weatherClass, request: Request):
#     session_result = await validate_session(request)
#     if isinstance(session_result, RedirectResponse):
#         return session_result
#     user_id = session_result['user_id']
#     cursor, db = connectdb()
#     cursor.execute("SELECT id, clothes FROM wardrobe WHERE user_id = %s", (user_id,))
#     items = cursor.fetchall()
#     db.close()



#     email = EMAIL
#     pid = PID

#     url = "https://ece140-wi25-api.frosty-sky-f43d.workers.dev/api/v1/ai/complete"
    
    
#     prompt = f"The temperature is {data.temp} with the weather being {data.cond}. My wardrobe has {items}, what do you suggest I wear? Can you respond only with the item name and not its id?"
#     ai_request_data = {
#         "prompt": prompt
#     }
    
#     headers = {
#         "email": email,
#         "pid": pid,
#         "Content-Type": "application/json"
#     }


#     try:
#         response = requests.post(url, json=ai_request_data, headers=headers)
        
#         if response.status_code == 200:
#             return response.json()  
#         else:
#             raise HTTPException(status_code=response.status_code, detail="Error from AI service")
    
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error making request to AI service: {e}")



getTables()



if __name__ == "__main__":
   uvicorn.run(app="app.main:app", host="0.0.0.0", port=6543, reload=True)
   