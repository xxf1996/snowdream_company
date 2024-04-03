# 需求分析师

from typing import Optional
from metagpt.actions import Action
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles.role import RoleContext
from snowdream_company.roles.restorable_role import RestorableRole
from snowdream_company.actions.restorable_action import RestorableAction

class DemandAnalysis(RestorableAction):
  """
  需求分析和整理行为；根据和用户之间的沟通记录，整理出完整的需求列表。
  """
  PROMPT_TEMPLATE: str = """
  这里有一个来自你和用户之间的对话记录（其中you代表你，user代表用户）：{instruction}。
  你需要根据这个对话记录分析其中已经明确的以及潜在的任务需求，请用JSON数组的形式返回一个需求列表。
  """

  name: str = "DemandAnalysis"

  async def run(self, instruction: str):
    if self.need_restore and self.finished:
      return instruction
    prompt = self.PROMPT_TEMPLATE.format(instruction=instruction)
    res = await self._aask(prompt)

    return res

class DemandComuniacate(RestorableAction):
  """
  需求沟通行为；与人类（用户）进行需求细节的沟通。
  """
  name: str = "DemandComuniacate"
  role: Optional[RestorableRole] = None
  PROMPT_TEMPLATE: str = """
  这里有一个来自你和用户之间的对话记录（其中you代表你，user代表用户）：{history}。
  你需要针对有疑惑的地方，询问用户具体的需求细节，如果你觉得目前的需求已经很明确了，直接回答END。
  你不用说出自己的名字，直接说出你的询问内容。
  """

  async def run(self, instruction: str, role: RestorableRole):
    if self.need_restore and self.finished:
      return instruction

    self.role = role

    if self.need_restore:
      res = await self.restore()
      return res
    res = await self.get_communication()

    return res

  async def get_communication(self):
    """
    获取当前角色询问的内容
    """
    history = self.get_history()
    prompt = self.PROMPT_TEMPLATE.format(history=history)

    logger.info("询问中……")
    question = await self._aask(prompt)

    # 记录交流的内容
    communication_msg = Message(content=question, role=self.role.profile, cause_by=self.name)
    self.role.add_memory(communication_msg)

    if question == "END":
      return self.get_history()

    res = await self.get_user_answer()

    return res

  async def get_user_answer(self):
    """
    获取用户的回答
    """
    user_content = input("你的回答（end代表没有问题了）：")
    use_msg = Message(content=user_content, role="user", cause_by=self.name)
    self.role.add_memory(use_msg)

    if user_content == "end":
      return self.get_history()

    res = await self.get_communication()

    return res

  async def restore(self):
    """
    恢复之前的沟通
    """
    memories = self.role.rc.memory.get()
    related_memories = [memory for memory in memories if memory.cause_by == self.name]
    last_memory = related_memories[-1]

    if last_memory.role == "user":
      res = await self.get_communication()
      return res

    logger.info("询问中……")
    logger.info(last_memory.content)
    res = await self.get_user_answer()

    return res


  def get_history(self):
    """
    获取角色和用户之间的沟通记录
    """
    records: list[str] = []
    memories = self.role.rc.memory.get()

    for memory in memories:
      role = memory.role if memory.role == "user" else "you"
      records.append(f"{role}: {memory.content}")

    return "\n".join(records)



class DemandAnalyst(RestorableRole):
  """
  需求分析师
  """
  name: str = "李莉"
  profile: str = "demand analyst"
  goal: str = "help users analyze and supplement demand"

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.set_actions([DemandComuniacate, DemandAnalysis])
    self._set_react_mode(react_mode="by_order")

  async def _act(self) -> Message:
    if self.need_restore_action:
      res = await self.restore_action()
      return res

    logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
    todo = self.rc.todo
    msg = self.get_memories(k=1)[0]
    answer = ''
    self.update_state(todo)
    if isinstance(todo, DemandComuniacate):
      answer = await todo.run(msg.content, role=self)
      todo.role = None # NOTICE: 避免保存action时序列化role内容
    else:
      answer = await todo.run(msg.content)

    record = Message(content=answer, role=self.profile, cause_by=type(todo))
    self.update_state(todo, True)
    if not self.restoring_action:
      self.add_memory(record)

    return record
