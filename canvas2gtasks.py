"""
Joe Villegas (joevillegasisawesome@gmail.com), 11/6/18.

Application for syncing Canvas Assignments (To-Dos)
with Google Calendar Tasks.

Requires Google and Canvas API Client Keys and Packages (Look at readme.txt)
PACKAGES REQUIRED:
    CanvasAPI (https://github.com/ucfopen/canvasapi)
    Google API Client (https://developers.google.com/tasks/quickstart/python)

Special thanks to Google (Tasks API) and ucfopen's Canvas API for making this pleasant!
"""

from __future__ import print_function
import os
import re
import fileinput
import datetime
import itertools

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

from canvasapi import Canvas

#   If modifying these scopes, delete the file token.json.
SCOPES = 'https://www.googleapis.com/auth/tasks'

TASKLIST_ID = ''


def main():
    os.chdir('user')

    """ Google API Authorization """
    google_service = auth_google_tasks()

    """ Canvas API Authorization """
    #   Canvas API URL and Key
    CANVAS_API_URL = "https://canvas.instructure.com"
    CANVAS_API_KEY = auth_canvas()

    canvas = Canvas(CANVAS_API_URL, CANVAS_API_KEY)

    """ Program start - Task List and To-Do List fetch """

    tasklists = google_service.tasklists().list().execute()
    print("✔ User authorized with Google account.")
    canvas_user = canvas.get_current_user()
    print("✔ User authorized with Canvas account.")
    course_list = get_courses(canvas_user)

    print("\nFinding assignments in Canvas...")
    course_ids = []
    for course in course_list:
        id = get_item_id(course)
        course_ids.append(id)

    assignments = get_assignment_dictionary(
        course_list, canvas_user, canvas, False, True)

    if get_google_canvas_list(tasklists, google_service) is not None:
        print("\n###   Canvas-2-GTasks is ready!   ###")

    print("\nSyncronizing your assignments with your GTasks list...")
    sync_result = synchronize_lists(
        assignments, tasklists, google_service)
    if sync_result:
        print("\n✔ Lists synchronized.")


""" Authorizations """


def auth_google_tasks():
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    return build('tasks', 'v1', http=creds.authorize(Http()))


def auth_canvas():
    user_keys_file = open("apikeys.txt", "r")
    user_keys_temp = user_keys_file.readlines()
    # print(user_keys_temp)
    canvas_key = user_keys_temp[3]

    # print(canvas_key)
    if (canvas_key == "<PLACEHOLDER>" or len(canvas_key) != 67):
        canvas_key = prompt_canvas_key()
        user_keys_temp[3] = canvas_key
        new_data = "".join(user_keys_temp)

        # print(new_data)

        with open("apikeys.txt", "w") as newfile:
            newfile.write(new_data)
            newfile.close()
        user_keys_file.close()

        return canvas_key
    else:
        user_keys_file.close()

        return canvas_key


def prompt_canvas_key():
    while True:
        key = input("Enter in your Canvas API Key: ")
        if (len(key) == 67):
            return key
        else:
            print("Invalid key. (Did you include '10~'?)")


def get_sample_course(course_list, canvas):
    #print("Sample course: " + course)

    return canvas.get_course(get_item_id(course_list[0]))


""" Functions for Canvas-2-GTasks """


def get_google_canvas_list(tasklists, service, debug=False):
    global TASKLIST_ID

    #print("\nGoogle Tasks list:")

    for tasklist in tasklists.get('items', []):

        # print(tasklist.get('title'))

        if tasklist.get('title') == "Canvas Assignments":
            TASKLIST_ID = (tasklist.get('id'))
            # print(TASKLIST_ID)
            print("\nCanvas Assignments list found!")
            return tasklist

    result = service.tasklists().insert(body={
        'title': 'Canvas Assignments'
    }).execute()
    TASKLIST_ID = tasklist.get('id')

    print(result['title'] + " was made")


def get_courses(canvas_user, all_courses=False):
    course_list = canvas_user.get_courses(
        enrollment_state='active', include='term')
    if all_courses:
        course_list = canvas_user.get_courses()

    # for course in course_list:
        # print(course)

    return course_list


def get_assignment_dictionary(course_list, canvas_user, canvas,
                              include_past=False, debug=False):
    user_assignments = []
    assignment_dict = {}

    for course in course_list:
        course_name = strip_id(course)
        if include_past:
            course_assignments = canvas_user.get_assignments(
                get_item_id(course))
            for ass in course_assignments:
                assignment_dict['title'] = strip_id(ass)
                assignment_dict['id'] = get_item_id(ass)
                assignment_dict['course'] = course_name
                #   TODO: CHECK
                try:
                    assignment_dict['complete'] = ass.get_submission(
                        include='submission_history')
                except:
                    assignment_dict['complete'] = False

                user_assignments.append(assignment_dict.copy())
        else:
            course_assignments = canvas_user.get_assignments(
                get_item_id(course), bucket='upcoming')
            for ass in course_assignments:
                assignment_dict['title'] = strip_id(ass)
                assignment_dict['id'] = get_item_id(ass)
                assignment_dict['course'] = course_name
                assignment_dict['complete'] = item_in_both_lists_as_string(
                    ass, course_assignments, canvas_user.get_assignments(
                        get_item_id(course), bucket='unsubmitted'))
                #   TODO: CHECK
                # print(ass)
                #print("Is completed: " + str(assignment_dict['complete']))

                #   TEST
                test_list = canvas_user.get_assignments(
                    get_item_id(course), bucket='unsubmitted')
                for test in test_list:
                    print(test)

                user_assignments.append(assignment_dict.copy())

        #print("\nUpcoming assignments: ")
        # for i in user_assignments:
            # print(i)

    return user_assignments


def get_unsubmitted_upcoming_assignments(course_list, canvas_user, canvas):
    assignment_list = []

    for course in course_list:
        course_name = strip_id(course)
        course_assignments = canvas_user.get_assignments(
            course, bucket={'upcoming', 'unsubmitted'}, include='submission')
        for ass in course_assignments:
            assignment_list.append(str(ass) + " - " + course_name)

    return assignment_list


def get_saved_tasks(google_list, google_service):
    results = google_service.tasklists().list(maxResults=10).execute()
    return results.get('items', [])


def synchronize_lists(canvas_list, google_list, google_service):
    #   TODO: Update existing entries with completed status and check 'non_present and completed' code
    google_list = google_service.tasks().list(tasklist=TASKLIST_ID).execute()
    google_list = google_list.get('items', [])

    print("\nAssignments found:\n")

    for assignment in canvas_list:
        time_completed = datetime.datetime.now().isoformat()  # TODO: get actual date
        not_present = True

        assignment_string = str(
            assignment['title'] + " - " + assignment['course'])

        print(assignment_string)
        if assignment['complete'] != False:
            print(" Completed at: " + assignment['complete'])
        else:
            continue
            #print(" Not yet completed")

        #print("Canvas: " + assignment)
        for task in google_list:
            #print("Google: " + task['title'])
            if assignment_string in task['title']:
                not_present = False

        #print("Is not present in Google: " + str(not_present))
        if not_present:
            # if assignment['complete'] != False:
                # google_service.tasks().insert(
                    # tasklist=TASKLIST_ID,
                    # body={'title': assignment_string, 'complete': str(time_completed)}).execute()
            # else:
            google_service.tasks().insert(
                tasklist=TASKLIST_ID, body={'title': assignment_string}).execute()
    return True


def get_item_id(item):
    item = str(item)
    start = item.find('(') + 1
    end = item.find(')', start)
    item = str(item[start:end])

    #print("Fetched item id: " + item)

    return item


def strip_id(item):
    item = str(item)
    return item[0:(item.find(' ('))]


def item_in_both_lists_as_string(item, list_1, list_2):
    #print("Comparing items: ")
    for i in list_1:
        # print(i)
        for j in list_2:
            print("against ")
            print(j)
            print(str(i) + "] v [" + str(j))
            if str(i) == str(j) and str(i) == str(item):
                return True
    return False


""" inside jokes """


def separate_words(text):
    text = str(text).replace(' ', '\n')
    print(text)


def init_path():
    __location__ = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__)))
    return __location__


if __name__ == '__main__':
    # init_path()

    main()
