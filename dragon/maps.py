# created with opprotoc 

status_map = {
    0: "OK",
    1: "Conflict",
    2: "Unsupported Type",
    3: "Bad Request",
    4: "Internal Error",
    5: "Command Not Found",
    6: "Service Not Found",
    7: "Out Of Memory",
    8: "Service Not Enabled",
    9: "Service Already Enabled",
    }

format_type_map = {
    0: "protocol-buffer",
    1: "json",
    2: "xml"
    }

message_type_map = {
    1: "command", 
    2: "response", 
    3: "event", 
    4: "error"
    }

message_map = {}
