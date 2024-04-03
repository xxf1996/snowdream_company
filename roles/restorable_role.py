# 可恢复记忆的角色
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.actions import Action
import os
import json
from typing import Any
from abc import abstractmethod
from snowdream_company.actions.restorable_action import RestorableAction

class RestorableRole(Role):
  """
  可恢复记忆的角色
  """
  __memory_path: str = ""
  __project_path: str = ""
  __skip_ask = True

  """是否跳过恢复记忆的询问"""
  need_restore_action: bool = False
  """当前角色是否需要恢复行为"""
  restoring_action: bool = False
  """是否正在恢复行为"""
  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.__project_path = kwargs["project_path"] or ""
    self.restore_memory()

  def restore_memory(self):
    """
    恢复记忆
    """
    memory_path = os.path.join(self.__project_path, "memory", f"{self.name}_{self.profile}.json")
    self.__memory_path = memory_path
    if not os.path.exists(memory_path):
      logger.info(f"{memory_path} 文件不存在，无法恢复记忆")
      self._init_memory()
      return

    if not self.__skip_ask:
      need_restore = input(f"{self.name}({self.profile})存在记忆，是否需要恢复记忆? (y/n): ")
      if need_restore.lower() != "y":
        # TODO: 应该要清空记忆？
        return

    with open(memory_path, "r", encoding="utf-8") as file:
      records: list[dict[str, Any]] = json.load(file)
      for record in records:
        msg = Message.model_validate(record)
        self.rc.memory.add(msg)
      logger.info(f"{self.name}({self.profile}): 恢复记忆 {len(records)} 条")

    self.check_need_restore_action() # NOTICE: 如果记忆都没有恢复就无需恢复动作了

  def get_action(self, state: dict[str, Any]) -> Action:
    """
    根据state.json记录的信息，从注册的action列表里获取到记录的action class
    """
    action_class = [action for action in self.actions if action.name == state["action_name"]][0]
    return action_class.model_validate(state["action"])

  def check_need_restore_action(self):
    """
    检查当前角色是否需要恢复行为
    """
    state_path = os.path.join(self.__project_path, "state.json")
    if not os.path.exists(state_path):
      self._init_state()
      return
    with open(state_path, "r", encoding="utf-8") as file:
      state: dict[str, Any] = json.load(file)
      if state["role"] == self.profile and state["name"] == self.name:
        self.need_restore_action = True

  async def restore_action(self):
    """
    根据state.json记录的信息，恢复之前的Action
    """
    state_path = os.path.join(self.__project_path, "state.json")
    with open(state_path, "r", encoding="utf-8") as file:
      state: dict[str, Any] = json.load(file)
      # 不是记录的行为直接跳过
      if self.todo.name != state["action_name"]:
        return self.rc.memory.get(k=1)[0]
      self.rc.memory.delete_newest()
      action = self.get_action(state)
      if isinstance(action, RestorableAction):
        action.to_restore(state["finished"])
        logger.info(f"{action.name}: 开始恢复之前的行为")
      else:
        logger.info(f"{action.name}不是可恢复的")
      self.set_todo(action)
      self.need_restore_action = False # 开始进行恢复
      self.restoring_action = True
      res = await self._act()
      self.restoring_action = False

      return res



  def add_memory(self, msg: Message):
    """
    添加一条记忆，并更新记忆文件
    """
    self.rc.memory.add(msg)
    self.update_memory()


  def update_memory(self):
    """
    将当前角色的memory同步到记忆文件中
    """
    if not os.path.exists(self.__memory_path):
      self._init_memory()
    records: list[dict[str, Any]] = [memory.model_dump() for memory in self.rc.memory.get()]
    with open(self.__memory_path, "w", encoding="utf-8") as file:
      json.dump(records, file)

  def update_state(self, action: Action, finished: bool = False):
    """
    基于当前角色和当前进行的行为更新state.json
    """
    state_path = os.path.join(self.__project_path, "state.json")
    if not os.path.exists(state_path):
      self._init_state()
    with open(os.path.join(self.__project_path, "state.json"), "w", encoding="utf-8") as file:
      json.dump({
        "role": self.profile,
        "name": self.name,
        "action_name": action.name,
        "action": action.model_dump(),
        "finished": finished,
      }, file)


  def _init_memory(self):
    """
    初始化记忆文件
    """
    with open(self.__memory_path, "w", encoding="utf-8") as file:
      file.write("[]")

  def _init_state(self):
    """
    初始化state.json
    """
    state_path = os.path.join(self.__project_path, "state.json")
    init_state = {
      "role": "",
      "name": "",
      "action_name": "",
      "action": "",
      "finished": False
    }
    with open(state_path, "w", encoding="utf-8") as file:
      json.dump(init_state, file)
