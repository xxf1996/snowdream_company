from metagpt.actions import Action

def is_same_action(type_name: str, action_type: str):
  return type_name in action_type or action_type in type_name