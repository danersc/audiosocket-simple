import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_user_state(id: str):
    data = r.get(id)
    return json.loads(data) if data else {"intent": {}, "history": []}

def update_user_state(user_id: str, intent=None, message=None):
    state = get_user_state(user_id)
    if intent:
        state["intent"].update(intent)
    if message:
        state["history"].append(message)
    r.set(user_id, json.dumps(state))

def clear_user_state(user_id: str):
    r.delete(user_id)
