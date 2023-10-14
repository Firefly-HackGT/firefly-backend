import asyncio
import http
import secrets
import signal
import json
from Section import Section

import websockets

SESSIONS = {}

async def error(websocket, error_type):
    """
    Send an error message.

    """
    event = {
        "type": "error",
        "error_type": error_type,
    }
    await websocket.send(json.dumps(event))

async def get_current_section(student_connection, section, curr, length):
    """
    Send the current section to the newly joined student.

    """
    event = {
        "type": "next_section",
        "name": section['name'],
        "description": section['description'],
        "curr": curr,
        "length": length
    }
    await student_connection.send(json.dumps(event))

async def rate(websocket, index, students_ratings, name, professor_connection):
    """
    Receive and process rating from student.

    """
    async for message in websocket:
        event = json.loads(message)
        students_ratings[name][index] = event['rating']
        section_ratings = [student_rating[index] for student_rating in students_ratings.values()]
        average_rating = sum(section_ratings) / len(section_ratings)
        event = {
            "type": "new_overall_rating",
            "overall_rating": average_rating
        }
        professor_connection.send(json.dumps(event))


async def join(websocket, session_key, name):
    """
    Handle a connection from a student to join an existing session.

    """
    # Find the lecture
    try:
        professor_connection, student_connections, sections, curr_section_index, student_ratings = SESSIONS[session_key]
        if name in student_ratings:
            raise LookupError() 
        student_ratings[name] = [1]*len(sections)
    except KeyError:
        await error(websocket, "LectureNotFound")
        return
    except LookupError:
        await error(websocket, "RepeatName")
        return
    # Register to receive when the professor changes sections.
    student_connections.add(websocket)
    try:
        # Send the current section the lecture is in.
        await get_current_section(websocket, sections[curr_section_index], curr_section_index, len(sections))
        # Receive and process rating from student.
        await rate(websocket, curr_section_index, student_ratings, name, professor_connection)
    finally:
        student_connections.remove(websocket)

async def control_sections(sections, curr, professor_connection, student_connections):
    """
    Receive and move to the next section of the professor.
    
    """
    async for message in professor_connection:
        curr += 1
        event = {
            "type": "next_section",
            "name": sections[curr]['name'],
            "description": sections[curr]['description'],
            "curr": curr,
            "length": len(sections)
        }
        websockets.broadcast(student_connections, json.dumps(event))


async def start_lecture(websocket, sections):
    """
    Handle a connection from the professor to start the lecture.

    """
    student_ratings = {}
    student_connections = {}
    professor_connection = websocket
    curr = 0

    session_key = secrets.token_urlsafe(5)
    SESSIONS[session_key] = professor_connection, student_connections, sections, curr, student_ratings

    try:
        # Send the secret access tokens to the browser of the first player,
        # where they'll be used for building "join" and "watch" links.
        event = {
            "type": "get_session_key",
            "session_key": session_key,
        }
        await websocket.send(json.dumps(event))
        # Receive and process moves from the first player.
        await control_sections(sections, curr, professor_connection, student_connections)
    finally:
        del SESSIONS[session_key]

async def handler(websocket):
    """
    Handle a connection and dispatch it according to who is connecting.

    """
    # Receive and parse the "init" event from the UI.
    message = await websocket.recv()
    event = json.loads(message)

    if event['type'] == "join_lecture":
        # Student joining session
        await join(websocket, event["session"], event["name"])
    elif event['type'] == "init_lecture":
        await start_lecture(websocket, event['sections'])


async def health_check(path, request_headers):
    """
    Used for Render to perform server health checks.
    """
    if path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK\n"


async def main():
    # Set the stop condition when receiving SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with websockets.serve(
        handler,
        host="",
        port=8080,
        process_request=health_check,
    ):
        await stop


if __name__ == "__main__":
    asyncio.run(main())