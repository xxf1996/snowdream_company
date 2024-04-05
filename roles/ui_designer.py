# UI设计师
from metagpt.schema import Message
from snowdream_company.roles.restorable_role import RestorableRole
from snowdream_company.roles.demand_analyst import DemandAnalysis, DemandConfirmationAsk
from snowdream_company.actions.restorable_action import RestorableAction
from metagpt.logs import logger
from snowdream_company.tool.type import is_same_action

class UIDesigner(RestorableRole):
  name: str = "斯蒂芬"
  profile: str = "ui designer"
  goal: str = "基于同事提供的需求为其提供相应的且合理的UI设计"

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.set_actions([DemandConfirmationAsk])
    self._set_react_mode(react_mode="react", max_react_loop=999)
    self.set_watch([DemandAnalysis])

  def state_machine(self):
    msg = self.get_memories(k=1)[0]

    logger.info(DemandAnalysis)

    if is_same_action(msg.cause_by, str(DemandAnalysis)):
      return self.get_action(DemandConfirmationAsk) # FIXME: 搞不懂这里之前没用实例为啥也可以？

    return None

  async def _act(self) -> Message:
    # TODO: 标准化act流程
    logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
    todo = self.rc.todo
    msg = self.get_memories(k=1)[0]
    answer = ''
    self.update_state(todo)

    if isinstance(todo, DemandConfirmationAsk):
      answer = await todo.run(self)
    else:
      answer = await todo.run(msg.content)

    record = Message(content=answer, role=self.profile, cause_by=type(todo))
    self.update_state(todo, True)
    # NOTICE: 仅正在恢复行为且之前行为已经结束的时候不需要保存记忆（因为之前记忆已经存在了）
    if not self.restoring_action or not todo.finished:
      self.add_memory(record)

    if isinstance(todo, RestorableAction):
      self.restoring_action = False
      self.need_restore_action = False
      RestorableRole.restorable = False # 恢复完成

    return record