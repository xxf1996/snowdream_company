# 需求分析师

from datetime import datetime
import json
import os
from typing import Any, Optional
from metagpt.actions import Action
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles.role import RoleContext
from snowdream_company.roles.restorable_role import RestorableRole
from snowdream_company.actions.restorable_action import RestorableAction
from snowdream_company.tool.markdown import demands_to_markdown, get_lang_content
from metagpt.actions.add_requirement import UserRequirement
from snowdream_company.tool.type import is_same_action

class DemandAnalysis(RestorableAction):
  """
  需求分析和整理行为；根据和用户之间的沟通记录，整理出完整的需求列表。
  """
  # PROMPT_TEMPLATE: str = """
  # 请根据我们上面之间的沟通，分析和整理出其中已经明确的以及潜在的任务需求，需求的拆分要尽可能地细化，包含各种边界条件。请用JSON数组的形式返回一个需求列表，每个需求都是一个JSON对象，对象包含“优先级”、“标题”和“需求描述”这几个字段，如果需求包含子需求，则可以增加一个“子需求”的字段，存放子需求列表。其中“需求描述”要尽可能的详尽和尽可能多的实现细节，使用明确的语言进行描述，以便实现的时候没有歧义。
  # """
  PROMPT_TEMPLATE: str = """
  请根据我们之前的沟通，请一步一步思考总结出涉及到的详细的业务流程，要穷举所有会发生的情况，包括各种边界条件触发时的情况；最终的业务流程图请基于mermaid的flowchart语法进行描述，以下是一个使用mermaid的flowchart语法描述流程图的示例：

  ```mermaid
  flowchart LR
    A[Hard edge] -->|Link text| B(Round edge)
    B --> C{Decision}
    C -->|One| D[Result one]
    C -->|Two| E[Result two]
  ```

  然后基于总结出的业务流程，按照涉及到的具体功能点进行需求拆分，然后总结出一份详细的需求列表。请用JSON数组的形式返回这个需求列表，每个需求都是一个JSON对象，对象包含“优先级”、“标题”和“需求描述”这几个字段，如果需求包含子需求，则可以增加一个“子需求”的字段，存放子需求列表。其中“需求描述”要尽可能的详尽和尽可能多的实现细节，使用明确的语言进行描述，以便实现的时候没有歧义，每段“需求描述”都不能少于50个字。
  """

  name: str = "DemandAnalysis"

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content

    history = self.get_history(role.rc.memory.get())
    prompt = {
      "role": "user",
      "content": self.PROMPT_TEMPLATE
    }

    answer = await self.llm.aask(
      msg=history + [prompt],
      system_msgs=[role.get_system_msg()]
    )
    res: str = get_lang_content(answer)

    self.save_doc(role.get_project_path(), answer)

    return res

  def get_history(self, memories: list[Message]):
    records: list[dict[str, str]] = []
    
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandComuniacate)):
        if memory.role == "user" and memory.content == "end":
          continue
        role = "user" if memory.role == "user" else "assistant"
        records.append({
          "role": role,
          "content": memory.content
        })
        # TODO: 需要对end的消息进行处理
      if is_same_action(memory.cause_by, str(UserRequirement)):
        records.append({
          "role": "user",
          "content": memory.content
        })

    return records

  def save_doc(self, project_path: str, answer: str):
    demand_json = get_lang_content(answer)
    flow_chat = get_lang_content(answer, lang="mermaid")
    demands: list[dict[str, Any]] = json.loads(demand_json)
    demand_content = demands_to_markdown(demands)
    doc_path = os.path.join(project_path, "prd", "1.0.0.md")
    doc = f"# 业务流程图\n\n{flow_chat}\n\n{demand_content}"

    with open(doc_path, "w", encoding="utf-8") as f:
      f.write(doc)


class DemandComuniacate(RestorableAction):
  """
  需求沟通行为；与人类（用户）进行需求细节的沟通。
  """
  name: str = "DemandComuniacate"
  role: Optional[RestorableRole] = None
  SYSTEM_PROMPT: str = """{system}

  你需要根据你和用户的对话记录，针对有疑惑的地方，询问用户具体的需求细节，如果你觉得目前的需求已经很明确了，直接回答end（即只有end这一个词）。
  你不用说出自己的名字，直接说出你的询问内容。
  """

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg

    self.role = role

    if self.need_restore:
      res: Message = await self.restore()
      return res

    res: Message = await self.get_communication()
    return res

  async def get_communication(self):
    """
    获取当前角色询问的内容
    """
    history = self.get_history()
    system_msg = self.SYSTEM_PROMPT.format(system=self.role.get_system_msg())

    logger.info("询问中……")
    question = await self.llm.aask(
      system_msgs=[system_msg],
      msg=history
    )

    # 记录交流的内容
    communication_msg = Message(content=question, role=self.role.profile, cause_by=type(self))
    self.role.add_memory(communication_msg)

    if question == "end": # 沟通结束
      return communication_msg

    res = await self.get_user_answer()

    return res

  async def get_user_answer(self):
    """
    获取用户的回答
    """
    user_content = input("你的回答（end代表没有问题了）：")
    use_msg = Message(content=user_content, role="user", cause_by=type(self))
    self.role.add_memory(use_msg)

    if user_content == "end":
      return use_msg

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
    records: list[dict[str, str]] = []
    memories = self.role.rc.memory.get()

    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandComuniacate)):
        role = "user" if memory.role == "user" else "assistant"
        records.append({
          "role": role,
          "content": memory.content
        })
      if is_same_action(memory.cause_by, str(UserRequirement)):
        records.append({
          "role": "user",
          "content": memory.content
        })

    return records

class DemandConfirmationAnswer(RestorableAction):
  name: str = "DemandConfirmationAnswer"
  PROMPT_TEMPLATE: str = """{system}
  这里有一份你总结的需求列表（三个反引号之间）：```{doc}```。

  用户对其中的某些需求有疑问，根据你们的对话记录，你需要针对用户的询问进行回答。

  请注意，你的任务是写进行回答，而不是模仿聊天记录！不用说出你的名字。
  """

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content
    memories = role.rc.memory.get()
    # history = self.get_history(memories, last_msg.sent_from)
    doc = self.get_doc(memories)
    system_msg = self.PROMPT_TEMPLATE.format(system=role.get_system_msg(), doc=doc)

    res = await self.llm.aask(
      msg=self.get_history_messages(memories, last_msg.sent_from),
      system_msgs=[system_msg]
    )

    return res

  def get_history(self, memories: list[Message], name: str):
    records: list[str] = []
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandConfirmationAsk)) and memory.sent_from == name:
        records.append(f"other: {memory.content}")
      elif is_same_action(memory.cause_by, str(DemandConfirmationAnswer)):
        records.append(f"you: {memory.content}")
      else:
        continue

    return "\n".join(records)

  def get_history_messages(self, memories: list[Message], name: str):
    messages: list[dict[str, str]] = []
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandConfirmationAsk)) and memory.sent_from == name:
        messages.append({
          "role": "user",
          "content": memory.content
        })
      elif is_same_action(memory.cause_by, str(DemandConfirmationAnswer)):
        messages.append({
          "role": "assistant",
          "content": memory.content
        })
      else:
        continue

    return messages

  def get_doc(self, memories: list[Message]):
    docs = [memory for memory in memories if is_same_action(memory.cause_by, str(DemandAnalysis))]
    return docs[-1].content


class DemandConfirmationAsk(RestorableAction):
  name: str = "DemandConfirmationAsk"
  PROMPT_TEMPLATE: str = """{system}
  这里有一份需求列表（三个反引号之间）：```{doc}```。

  你需要从你负责的工作职能出发，主要关注{focus}方面即可！根据以上提供的需求列表以及你和用户的对话记录，找到这些需求在{focus}方面存在的疑问和细节问题，对用户进行提问，请写出你的提问内容。

  请注意，不用说出你的名字。如果没有疑问或者想结束询问，直接回答end（即只有end这一个词）即可！
  """

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content
    memories = role.rc.memory.get()
    # history = self.get_history(memories, last_msg.sent_from)
    doc = self.get_doc(memories)
    system_msg = self.PROMPT_TEMPLATE.format(system=role.get_system_msg(), doc=doc, focus=role.focus)

    # res = await self._aask(prompt, role.get_system_msg())
    res = await self.llm.aask(
      msg=self.get_history_messages(memories, last_msg.sent_from),
      system_msgs=[system_msg]
    )

    return res

  def get_history(self, memories: list[Message], name: str):
    records: list[str] = []
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandConfirmationAnswer)) and memory.sent_from == name:
        records.append(f"other: {memory.content}")
      elif is_same_action(memory.cause_by, str(DemandConfirmationAsk)):
        records.append(f"you: {memory.content}")
      else:
        continue

    return "\n".join(records)

  def get_history_messages(self, memories: list[Message], name: str):
    messages: list[dict[str, str]] = [
      {
        "role": "user",
        "content": "你对需求列表有什么疑问吗？"
      }
    ]
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandConfirmationAnswer)) and memory.sent_from == name:
        messages.append({
          "role": "user",
          "content": memory.content
        })
      elif is_same_action(memory.cause_by, str(DemandConfirmationAsk)):
        messages.append({
          "role": "assistant",
          "content": memory.content
        })
      else:
        continue

    return messages

  def get_doc(self, memories: list[Message]):
    docs = [memory for memory in memories if is_same_action(memory.cause_by, str(DemandAnalysis))]
    return docs[-1].content


class DemandChange(RestorableAction):
  """需求变更"""
  name: str = "DemandChange"
  SYSTEM_TEMPLATE: str = """{system}
  这里有一份你之前总结的需求列表（三个反引号之间）：```{doc}```。
  """

  PROMPT_TEMPLATE: str = """我这边暂时没问题了，你需要结合之前的需求列表以及我们的对话中双方确认好的细节问题，思考总结出新的业务流程，业务流程要尽可能地详细；最终的业务流程图请基于mermaid的flowchart语法进行描述，以下是一个使用mermaid的flowchart语法描述流程图的示例：

  ```mermaid
  flowchart LR
    A[Hard edge] -->|Link text| B(Round edge)
    B --> C{Decision}
    C -->|One| D[Result one]
    C -->|Two| E[Result two]
  ```

  然后基于总结出的业务流程加上对话中双方确认好的细节，按照涉及到的具体功能点进行需求拆分，然后总结出一份新的需求列表。请用JSON数组的形式返回一个需求列表，每个需求都是一个JSON对象，对象包含“优先级”、“标题”和“需求描述”这几个字段，如果需求包含子需求，则可以增加一个“子需求”的字段，存放子需求列表；其中“需求描述”要尽可能的详尽和尽可能多的实现细节，以便实现的时候没有歧义。

  同时请用一段文字说明需求文档变动的内容，重点关注变动项，文字尽可能简洁明确一点；这段文字请按照markdown的代码块格式进行包裹，代码块内不需要任何的markdown标题！代码语言设置为demand-change。

  请注意demand-change代码块和json代码块之间要完全区分开！不要互相包含！请保证各个代码块是完整的！
  """
  # FIXME: 沟通确认的细节完全没有加入到新的需求列表中

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content
    memories = role.rc.memory.get()
    doc = self.get_doc(memories)
    system_msg = self.SYSTEM_TEMPLATE.format(system=role.get_system_msg(), doc=doc)

    answer = await self.llm.aask(
      msg=self.get_history_messages(memories, last_msg.sent_from),
      system_msgs=[system_msg]
    )

    res = self.save_doc(role.get_project_path(), answer)

    return json.dumps(res)

  def get_doc(self, memories: list[Message]):
    docs = [memory for memory in memories if is_same_action(memory.cause_by, str(DemandAnalysis))]
    return docs[-1].content

  def get_history_messages(self, memories: list[Message], name: str):
    messages: list[dict[str, str]] = []
    for memory in memories:
      if is_same_action(memory.cause_by, str(DemandConfirmationAsk)) and memory.sent_from == name:
        messages.append({
          "role": "user",
          "content": memory.content if memory.content != "end" else self.PROMPT_TEMPLATE
        })
      elif is_same_action(memory.cause_by, str(DemandConfirmationAnswer)):
        messages.append({
          "role": "assistant",
          "content": memory.content
        })
      else:
        continue

    return messages

  def save_doc(self, project_path: str, answer: str):
    demand_json = get_lang_content(answer)
    demands: list[dict[str, Any]] = json.loads(demand_json)
    demand_change = get_lang_content(answer, lang="demand-change")
    demand_content = demands_to_markdown(demands)
    now = datetime.now()
    formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")

    doc = f"# 需求变更记录\n\n## {formatted_time}\n\n{demand_change}\n\n{demand_content}"
    doc_path = os.path.join(project_path, "prd", "1.0.0.md")
    with open(doc_path, "w", encoding="utf-8") as f:
      f.write(doc)

    return {
      "demands": demand_json,
      "demand_change": {
        "version": "1.0.0",
        "content": demand_change,
        "time": formatted_time
      }
    }


class DemandAnalyst(RestorableRole):
  """
  需求分析师
  """
  name: str = "李莉"
  profile: str = "demand analyst"
  goal: str = "帮助用户分析需求及补充相关的需求"

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.set_actions([DemandComuniacate, DemandAnalysis, DemandConfirmationAnswer, DemandChange])
    self._set_react_mode(react_mode="react", max_react_loop=999)
    watch_list: list[Action] = [DemandConfirmationAsk]
    if self.is_empty_state():
      watch_list.append(UserRequirement) # 如果没有之前执行的状态信息，说明刚开始，默认从用户需求进行触发
    self.set_watch(watch_list)

  def state_machine(self):
    msg = self.get_memories(k=1)[0]

    if is_same_action(msg.cause_by, str(UserRequirement)):
      return self.get_action(DemandComuniacate)

    if msg.sent_from == self.name and is_same_action(msg.cause_by, str(DemandComuniacate)):
      return self.get_action(DemandAnalysis)

    if msg.role == self.profile and is_same_action(msg.cause_by, str(DemandAnalysis)):
      return None

    # 正常的回答需求询问
    if is_same_action(msg.cause_by, str(DemandConfirmationAsk)) and msg.content != "end":
      return self.get_action(DemandConfirmationAnswer)

    # 需求询问结束
    if is_same_action(msg.cause_by, str(DemandConfirmationAsk)) and msg.content == "end":
      return self.get_action(DemandChange)

    return None

  async def _act(self) -> Message:
    logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
    todo = self.rc.todo
    msg = self.get_memories(k=1)[0]
    answer = ''
    send_to: list[str] = []
    self.update_state(todo)
    if isinstance(todo, DemandComuniacate):
      answer = await todo.run(role=self)
      todo.role = None # NOTICE: 避免保存action时序列化role内容
    elif isinstance(todo, DemandAnalysis):
      answer = await todo.run(self)
    elif isinstance(todo, DemandConfirmationAnswer):
      answer = await todo.run(self)
      # TODO: 针对answer应该需要针对具体的人，不然多人同时进行ask的时候就会出现问题
      send_to.append(msg.sent_from)
    elif isinstance(todo, DemandChange):
      answer = await todo.run(self)
      send_to.append(msg.sent_from)
    else:
      answer = await todo.run(msg.content)

    record = answer if isinstance(answer, Message) else Message(content=answer, role=self.profile, cause_by=type(todo))
    if len(send_to) > 0:
      record.send_to = set(send_to)

    if self.restoring_action and todo.finished:
      record = msg # TODO: 事实上所有恢复的已结束动作直接返回消息即可，无需再执行动作？

    self.update_state(todo, True)
    # NOTICE: 仅正在恢复行为且之前行为已经结束的时候不需要保存记忆（因为之前记忆已经存在了）
    if not self.restoring_action or not todo.finished and not isinstance(answer, Message):
      record = self.add_memory(record)

    if isinstance(todo, RestorableAction):
      self.restoring_action = False
      self.need_restore_action = False
      RestorableRole.restorable = False # 恢复完成
      todo.finished = False
      todo.need_restore = False

    return record
