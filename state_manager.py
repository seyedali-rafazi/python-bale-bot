#state_manager.py

user_states = {}

def set_state(chat_id, step, **kwargs):
    """تنظیم وضعیت کاربر به همراه داده‌های اضافی مثل لینک"""
    state_data = {'step': step}
    state_data.update(kwargs)
    user_states[chat_id] = state_data

def get_state(chat_id):
    """دریافت وضعیت فعلی کاربر (خروجی همیشه یک دیکشنری است)"""
    return user_states.get(chat_id, {})

def clear_state(chat_id):
    """پاک کردن وضعیت کاربر"""
    if chat_id in user_states:
        del user_states[chat_id]
