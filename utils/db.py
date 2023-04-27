import sqlite3

def execute_command(connection: sqlite3.Connection, command: str, params: tuple = None):
    cursor = connection.cursor()

    try:
        if params is None:
            cursor.execute(command)
        else:
            cursor.execute(command, params)
        connection.commit()
    except Exception as e:
        print("Failed to execute db command!")
        print("Command: \"{}\"".format(command))
        print("Parameters: \"{}\"".format(params))
        print("{}\n\n".format(e))
    
    cursor.close()

def get_data(connection: sqlite3.Connection, command: str, params: tuple = None):
    cursor = connection.cursor()

    rows = []
    try:
        if params is None:
            cursor.execute(command)
        else:
            cursor.execute(command, params)
        rows = cursor.fetchall()
    except Exception as e:
        print("Failed to get db data!")
        print("Command: \"{}\"".format(command))
        print("Params: \"{}\"".format(params))
        print("{}\n\n".format(e))

    
    cursor.close()
    return rows

def get_single_row(connection: sqlite3.Connection, command: str, params:tuple = None):
    data = get_data(connection, command, params)
    if data is None or len(data) == 0:
        return None
    return data[0]

def get_single_value(connection: sqlite3.Connection, command: str, params: tuple = None):
    data = get_single_row(connection, command, params)
    if data is None:
        return None
    return data[0]