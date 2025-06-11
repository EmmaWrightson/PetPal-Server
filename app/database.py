import pandas as pd
# Add the necessary imports
import mysql.connector as mysql
import os
import datetime
from dotenv import load_dotenv
import time
import logging
#import mysql.connector
from typing import Optional
from mysql.connector import Error


# Load environment variables
load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def connectdb():

    # Read Database connection variables

    db_host = os.environ['MYSQL_HOST']
    db_user = os.environ['MYSQL_USER']
    db_pass = os.environ['MYSQL_PASSWORD']
    db_name = os.environ['MYSQL_DATABASE']
    db = mysql.connect(user=db_user, password=db_pass, host=db_host, database=db_name,port = int(os.getenv('MYSQL_PORT', 3306)))
    cursor = db.cursor(dictionary=True)
    return cursor, db



# def connectdb():
#     # Read Database connection variables
#     db_host = os.environ['MYSQL_HOST']
#     db_user = os.environ['MYSQL_USER']
#     db_pass = os.environ['MYSQL_PASSWORD']
#     db_name = os.environ['MYSQL_DATABASE']
#     ssl_ca  = os.getenv('MYSQL_SSL_CA')  # Path to CA certificate file
    

#     db = mysql.connect(user=db_user, 
#                        port=int(os.getenv('MYSQL_PORT')),
#                        password=db_pass, 
#                        host=db_host, 
#                        database=db_name,
#                        ssl_ca=ssl_ca,
#                        ssl_verify_identity=True
#                        )

#     cursor = db.cursor(dictionary=True)
#     return cursor, db



async def setup_database(initial_users: dict = None):
    """Creates user, session, and new device-related tables, and populates initial user data if provided."""
    connection = None
    cursor = None

    #table schemas
    table_schemas = {
        "users": """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                location VARCHAR(255) NOT NULL
            )
        """,
        "sessions": """
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INT NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """,
        "user_devices": """
            CREATE TABLE IF NOT EXISTS user_devices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                device_topic VARCHAR(255) NOT NULL UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """,
        
    }

    try:
        #database connection
        cursor, connection = connectdb()  #unpack tuple

        
        #drop and recreate tables one by one  (U_DEVS AND WARDROBE NOT BEING CREATED)
        # for table_name in ["sensor_data","user_devices","sessions", "wardrobe", "sensor_temp","users"]:
        #     #drop table if exists
        #     logger.info(f"Dropping table {table_name} if exists...")
        #     cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        #     connection.commit()
        
        #recreate tables
        for table_name, create_query in table_schemas.items():
            try:
                #create table
                logger.info(f"Creating table {table_name}...")
                cursor.execute(create_query)
                connection.commit()
                logger.info(f"Table {table_name} created successfully")
            except Error as e:
                logger.error(f"Error creating table {table_name}: {e}")
                raise
                

        #Insert initial users if provided
        if initial_users:
            try:
                insert_query = "INSERT INTO users (name, password, location, email) VALUES (%s, %s, %s, %s)"
                for name, user_data in initial_users.items():
                    cursor.execute(insert_query, (name, user_data['password'], user_data['location'], user_data['email']))
                connection.commit()
                logger.info(f"Inserted {len(initial_users)} initial users")
            except Error as e:
                logger.error(f"Error inserting initial users: {e}")
                raise

    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        raise

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            logger.info("Database connection closed")



async def get_user_by_email(email: str) -> Optional[dict]:
    """Retrieve user from database by email."""
    connection = None
    cursor = None
    try:
        cursor, connection = connectdb()  
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# Database utility functions for user and session management
async def get_user_by_name(name: str) -> Optional[dict]:
    """Retrieve user from database by name."""
    connection = None
    cursor = None
    try:
        #connection = get_db_connection()
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE name = %s", (name,))
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


async def get_user_by_id(user_id: int) -> Optional[dict]:
    """
    Retrieve user from database by ID.

    Args:
        user_id: The ID of the user to retrieve

    Returns:
        Optional[dict]: User data if found, None otherwise
    """
    connection = None
    cursor = None
    try:
        #connection = get_db_connection()
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


async def create_session(user_id: int, session_id: str) -> bool:
    """Create a new session in the database."""
    connection = None
    cursor = None
    try:
        #connection = get_db_connection()
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, user_id) VALUES (%s, %s)", (session_id, user_id)
        )
        connection.commit()
        return True
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


async def get_session(session_id: str) -> Optional[dict]:
    """Retrieve session from database."""
    connection = None
    cursor = None
    try:
        #connection = get_db_connection()
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM sessions s
            WHERE s.id = %s
        """,
            (session_id,),
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


async def delete_session(session_id: str) -> bool:
    """Delete a session from the database."""
    connection = None
    cursor = None
    try:
        #connection = get_db_connection()
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor = connection.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        connection.commit()
        return True
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


#use in profile tab later

async def add_user_device(user_id: int, device_topic: str):
    """Associates a user with a device by adding a record in the user_device table."""
    connection = None
    cursor = None
    try:
        cursor, connection = connectdb()  # Unpack the returned tuple here
        cursor.execute("INSERT INTO user_devices (user_id, device_id) VALUES (%s, %s)", (user_id, device_topic))
        connection.commit()
        logger.info(f"User with ID {user_id} associated with device topic {device_topic}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

