import asyncio
import http
import secrets
import signal
import json

import websockets
from pymongo_user_functions import add_student_lecture, add_professor_lecture, get_professor_lectures, get_student_lectures

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

async def get_current_section(student_connection, rating, section, curr, lecture_name, length):
    """
    Send the current section to the newly joined student.

    """
    event = {
        "type": "next_section",
        "lecture_name": lecture_name,
        "section_name": section['name'],
        "description": section['description'],
        "rating": rating,
        "curr": curr,
        "length": length
    }
    await student_connection.send(json.dumps(event))

async def rate(websocket, lecture, students_ratings, name, professor_connection):
    """
    Receive and process rating from student.

    """
    async for message in websocket:
        event = json.loads(message)
        students_ratings[name][lecture['curr_section']] = event['rating']
        section_ratings = [student_rating[lecture['curr_section']] for student_rating in students_ratings.values()]
        average_rating = round(sum(section_ratings) / len(section_ratings), 1)
        event = {
            "type": "new_overall_rating",
            "overall_rating": average_rating,
            "num_students": len(students_ratings)
        }
        await professor_connection.send(json.dumps(event))


async def join(websocket, session_key, name):
    """
    Handle a connection from a student to join an existing session.

    """
    # Find the lecture
    try:
        professor_connection, student_connections, lecture, student_ratings = SESSIONS[session_key]
        if name in student_ratings:
            raise LookupError() 
        student_ratings[name] = [0]*len(lecture['sections'])
    
    except KeyError:
        await error(websocket, "LectureNotFound")
        return
    except LookupError:
        await error(websocket, "RepeatName")
        return
    # Register to receive when the professor changes sections.
    student_connections[name] = websocket
    try:
        #Update overall_rating when student first joins
        section_ratings = [student_rating[lecture['curr_section']] for student_rating in student_ratings.values()]
        average_rating = round(sum(section_ratings) / len(section_ratings), 1)
        event = {
            "type": "new_overall_rating",
            "overall_rating": average_rating,
            "num_students": len(student_ratings)
        }
        await professor_connection.send(json.dumps(event))
        # Send the current section the lecture is in.
        await get_current_section(websocket, student_ratings[name][lecture['curr_section']], lecture['sections'][lecture['curr_section']], lecture['curr_section'], lecture['name'], len(lecture['sections']))
        # Receive and process rating from student.
        await rate(websocket, lecture, student_ratings, name, professor_connection)
    finally:
        del student_connections[name]

async def control_sections(lecture, prof_name, professor_connection, student_connections, student_ratings):
    """
    Receive and move to the next section of the professor.
    
    """
    async for message in professor_connection:
        event = json.loads(message)
        if event['type'] == 'back':
            if lecture['curr_section'] == 0:
                continue
            lecture['curr_section'] -= 1
        else:    
            lecture['curr_section'] += 1
        if lecture['curr_section'] < len(lecture['sections']):
            for student_name in student_connections.keys():
                event = {
                    "type": "next_section",
                    "lecture_name": lecture['name'],
                    "section_name": lecture['sections'][lecture['curr_section']]['name'],
                    "description": lecture['sections'][lecture['curr_section']]['description'],
                    "rating":student_ratings[student_name][lecture['curr_section']],
                    "curr": lecture['curr_section'],
                    "length": len(lecture['sections'])
                }   
                await student_connections[student_name].send(json.dumps(event))
            section_ratings = [student_rating[lecture['curr_section']] for student_rating in student_ratings.values()]
            average_rating = 0
            if len(section_ratings) > 0:
                average_rating = round(sum(section_ratings) / len(section_ratings), 1)
            event = {
                "type": "new_overall_rating",
                "overall_rating": average_rating,
                "num_students": len(student_ratings)
            }
            await professor_connection.send(json.dumps(event))
        else:
            # If the sections are over send to students < 3 ratings and prof sections overal_ratings
            for student_name in student_connections.keys():
                sections_info = []
                overall_average_rating = 0
                if len(student_ratings[student_name]) > 0:
                    overall_average_rating = sum(student_ratings[student_name]) / len(student_ratings[student_name])
                db_lecture = {
                    "name": lecture['name'],
                    "avg_rating": overall_average_rating,
                    "sections": [None]*len(lecture['sections'])
                }
                for index, section_rating in enumerate(student_ratings[student_name]):
                    db_lecture['sections'][index] = {
                        "name": lecture['sections'][index]['name'],
                        "description": lecture['sections'][index]['description'],
                        "rating": section_rating
                    }
                    section_info = {}
                    section_info['name'] = lecture['sections'][index]['name']
                    section_info['description'] = lecture['sections'][index]['description']
                    section_info['rating'] = section_rating
                    sections_info.append(section_info)
                event = {
                    "type": "final_results",
                    "sections": sections_info
                }
                await student_connections[student_name].send(json.dumps(event))
                add_student_lecture(student_name, db_lecture)
            average_ratings = [0]*len(lecture['sections'])
            overall_average_rating = 0
            if len(student_ratings.values()) > 0:
                for index in range(len(lecture['sections'])):
                    section_ratings = [student_rating[index] for student_rating in student_ratings.values()]
                    average_ratings[index] = sum(section_ratings) / len(section_ratings)
                overall_average_rating = sum(average_ratings) / len(average_ratings)
            sections_info = []
            db_lecture = {
                    "name": lecture['name'],
                    "avg_rating":overall_average_rating,
                    "sections": [None]*len(lecture['sections'])
                }
            for index, average_rating in enumerate(average_ratings):
                db_lecture['sections'][index] = {
                    "name": lecture['sections'][index]['name'],
                    "description": lecture['sections'][index]['description'],
                    "rating": round(average_rating, 1)
                }
                section_info = {}
                section_info['name'] = lecture['sections'][index]['name']
                section_info['description'] = lecture['sections'][index]['description']
                section_info['rating'] = round(average_rating, 1)
                sections_info.append(section_info)
            event = {
                "type": "final_results",
                "sections": sections_info
            }
            await professor_connection.send(json.dumps(event))
            add_professor_lecture(prof_name, db_lecture)
            return
        


async def start_lecture(websocket, sections, lecture_name, prof_name):
    """
    Handle a connection from the professor to start the lecture.

    """
    student_ratings = {}
    student_connections = {}
    professor_connection = websocket
    lecture = {
        "name":lecture_name,
        "curr_section": 0,
        "sections": sections
    }

    session_key = secrets.token_urlsafe(5)
    SESSIONS[session_key] = professor_connection, student_connections, lecture, student_ratings

    try:
        # Send the secret access tokens to the browser of the first player,
        # where they'll be used for building "join" and "watch" links.
        event = {
            "type": "get_session_key",
            "session_key": session_key,
        }
        await websocket.send(json.dumps(event))
        # Receive and process moves from the first player.
        await control_sections(lecture, prof_name, professor_connection, student_connections, student_ratings)
    finally:
        del SESSIONS[session_key]
async def send_hist_data(websocket, person_type, name):
    event = {
        "type":"hist_data"
    }
    if person_type == 'Professor':
        event['lectures'] = get_professor_lectures(name)
    else:
        event['lectures'] = get_student_lectures(name)
    await websocket.send(json.dumps(event))
 
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
        await start_lecture(websocket, event['sections'], event['lecture_name'], event['prof_name'])
    elif event['type'] == 'get_hist_data':
        await send_hist_data(websocket, event['person_type'], event['name'])
        await websocket.wait_closed()


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