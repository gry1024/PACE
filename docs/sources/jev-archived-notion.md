# Jev for PACE · 本地快照

- 来源：https://app.notion.com/p/3f0f7be8670c80dcb7dff6c5a87d2c12?pvs=204
- 读取日期：2026-10-07（Asia/Shanghai）
- 源页面最后编辑：2026-10-07T08:55:35.492Z
- 状态：源页面已标记 deleted；仅作历史参考
- 格式：Notion enhanced Markdown；引用和图片未离线打包。
- 只读证据：变更本地决策请写 ADR，不要改写源文档。

---

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3f0f7be8670c80dcb7dff6c5a87d2c12 as of 2026-10-07T08:55:35.492Z:
<page url="https://app.notion.com/p/3f0f7be8670c80dcb7dff6c5a87d2c12" deleted>
<ancestor-path></ancestor-path>
<properties>
{"title":"Jev for PACE"}
</properties>
<iconMetadata>null</iconMetadata>
<content>
# Jev for PACE
<callout icon="🧠" color="blue_bg">
	**目标：只处理一个最小事件——一次连接。**
	给定一个发起者、一次 Connection Request 和一组 Candidate，PACE 用同一个 Selection Mechanism 判断：
	**应该连接谁，或者当前没有合适的人。**
</callout>
# 1. Matching Formalization
## 1.1 Entity
PACE 中任意可连接主体定义为：
$$
E_i=(O_i,D_i,S_i)
$$
其中：
- **O_i：Ontology**，主体长期本体，包括个人信息、兴趣、能力、经历、行为、偏好等；
- **D_i：Demand**，主体当前或长期存在的需求；
- **S_i：Supply**，主体当前或长期愿意提供的能力、商品、时间、活动机会、社交意愿等。
这些信息允许丰富、冗余、稀疏和缺失。
## 1.2 Connection Request
当主体 E_i 发起一次具体连接需求时，产生：
$$
R_i
$$
例如：
> 周六下午想找一个北大羽毛球搭子，中等水平，想打单打，希望水平接近。
一次连接的 requester 输入就是：
$$
(R_i,E_i)
$$
候选主体仍然保持统一形式：
$$
E_j=(O_j,D_j,S_j)
$$
MVP 不为羽毛球、约饭、求助、交易等场景设计不同 Schema，也不额外做 request-conditioned projection。
**先直接测试 Jev 是否能从 Candidate 的杂乱、冗余、缺失信息中自行识别与当前 Request 有关的部分。**
## 1.3 Candidate Set
给定候选集合：
$$
\mathcal{E}
=
\{E_1,E_2,\dots,E_K\}
$$
在 Jev Choice 中额外加入一个特殊选项：
$$
E_{\varnothing}
=
\text{No suitable match}
$$
因此实际选择空间为：
$$
\mathcal{E}^{+}
=
\mathcal{E}\cup\{E_{\varnothing}\}
$$
## 1.4 Jev Choice
PACE 调用 Jev：
$$
\operatorname{JevChoice}
(R_i,E_i,\mathcal{E}^{+})
\rightarrow
(p_1,\dots,p_K,p_{\varnothing})
$$
并满足：
$$
\sum_{j=1}^{K}p_j+p_{\varnothing}=1
$$
其中：
- p_j：Candidate j 在当前候选集合中被选为最佳连接对象的**相对概率**；
- p_empty：当前候选集合中**没有合适对象**的相对概率。
若：
$$
p_{\varnothing}
>
\max_j p_j
$$
则返回：
> **No Match**
否则：
$$
j^*
=
\arg\max_j p_j
$$
返回 Candidate j\*。
这里的 probability 是**当前 Candidate Set 内的相对选择概率**，不是现实世界中的绝对连接成功率。Candidate Set 改变，同一个 Candidate 的 probability 也可能改变。
## 1.5 最小流程
$$
E_i
\rightarrow
R_i
\rightarrow
\{E_j\}
\rightarrow
\operatorname{JevChoice}
\rightarrow
j^*\ \text{or No Match}
\rightarrow
Connection
$$
<callout icon="💡" color="green_bg">
	**PACE 初期算法原则**
	不为不同场景写不同 Matcher；不提前堆复杂规则；尽量让模型自己理解 Ontology / Demand / Supply 与 Request 的关系。
	底层始终只回答一个问题：
	**这个 Request，现在最应该连接谁？如果没有合适的人，就不连接。**
</callout>
---
# 2. 映射到 TypeSafe Jev SDK
PACE 使用官方 Python SDK（TypeSafe HTTP API 的 Python 封装。）：
`from typesafe_sdk import Choice, TypeSafeClient`
对 PACE：
- state = Requester Entity + Connection Request
- Choice.instructions = 统一的连接选择规则
- Choice.criteria = Candidate ID → Candidate 的 O / D / S 描述
- no_match = 额外 Choice option
返回结果直接提供：choice、probabilities、confidence。
MVP 实验使用 TypeSafeClient；正式 PACE Backend 建议使用 AsyncTypeSafeClient，便于后续并行处理多个 candidate group。
参考：[TypeSafe API](https://api.typesafe.ai/redoc) · [TypeSafe Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
---
# 3. 产品场景
场景只用于**产品入口、冷启动运营和效果分析**，不进入底层算法分支。
<table fit-page-width="true" header-row="true">
<tr>
<td>一级场景</td>
<td>本质</td>
<td>典型场景</td>
<td>示例 Request</td>
</tr>
<tr>
<td>**活动连接**</td>
<td>一起做某件事</td>
<td>运动、学习、娱乐、约饭、活动同行</td>
<td>“今晚找一个水平接近的羽毛球单打搭子。”</td>
</tr>
<tr>
<td>**协作 / 求助连接**</td>
<td>寻找能力、资源或角色补齐当前需求</td>
<td>技能求助、物品借用、临时帮忙、项目组队</td>
<td>“找一个组队《多模态学习》大作业的信科同学。”</td>
</tr>
<tr>
<td>**交易连接**</td>
<td>需求方与供给方围绕明确标的建立连接</td>
<td>二手、租赁、服务购买、交换</td>
<td>“想收一本这学期的信息论教材，今晚能面交。”</td>
</tr>
<tr>
<td>**关系连接**</td>
<td>建立关系本身就是目的</td>
<td>交友、兴趣社交、认识同行</td>
<td>“想认识也在做具身智能、愿意线下交流的同学。”</td>
</tr>
</table>
四类场景在算法层面完全一致：
$$
(R_i,E_i,\{E_j\})
\rightarrow
\operatorname{JevChoice}
\rightarrow
j^*\ \text{or No Match}
$$
---
# 4. 最小 SDK 实现
下面两个 Request 面对**同一个 Requester 和同一个固定 Entity Pool**。
Entity 不是围绕某个场景设计的数据结构，而是长期积累的开放世界主体信息。Request 可以突然出现，甚至此前从未出现在该用户的 Demand 中。
```python
import asyncio

from typesafe_sdk import AsyncTypeSafeClient, Choice


SELECTION_INSTRUCTIONS = """
Select the single candidate most likely to be the right counterpart
for the current Connection Request.

The Connection Request is the primary objective. It may describe a new,
temporary, or previously unseen situation. Do not assume that the request
must already exist in the requester's historical Demand.

Each candidate is a general-purpose Entity whose Ontology, Demand, and Supply
may contain information from many unrelated parts of life. Evaluate candidates
only by evidence relevant to the current request.

Rules:
1. Ignore information irrelevant to the current request.
2. Do not prefer a candidate merely because its profile is longer, richer,
   or contains more keywords overlapping with the request.
3. Do not invent or assume missing facts.
4. Distinguish hard requirements from soft preferences.
   Explicit requirements such as must, only, exact time, location, budget,
   compatibility, quantity, identity, or availability are decisive.
   Preferences such as prefer, ideally, or if possible affect ranking but
   must not override a hard requirement.
5. Judge actual counterpart fit, not semantic similarity alone.
6. Use Ontology to understand the entity, Demand to understand what it wants,
   and Supply to understand what it can currently provide. None of the three
   is guaranteed to contain request-relevant information.
7. Consider whether the connection can actually happen now.
8. A single important mismatch may outweigh many superficial matches.

Choose no_match if every candidate violates an important requirement,
or if there is not enough evidence to justify a suitable connection.
"""


requester = {
    "ontology": """
    北京大学本科生，男，大二，信息科学技术学院。
    平时住校，主要活动范围在燕园、五四体育中心、中关新园一带。
    会打羽毛球，水平约 3.5 级；平时也跑步、健身。
    喜欢周杰伦、陈奕迅、华语流行，也会唱一些粤语歌。
    喜欢摄影、科幻电影、咖啡，在做具身智能相关科研。
    常用 Windows + WSL 做开发。
    周末大多在学校，但安排变化比较大。
    """,
    "demand": """
    最近想认识做具身智能、机器人方向的同学；
    正在找一块二手 2TB SSD；
    偶尔想找稳定的羽毛球搭子。
    """,
    "supply": """
    可以帮忙看 Python / PyTorch / Linux 环境问题；
    有一些闲置教材和电子配件可以出；
    周末偶尔可以约运动。
    """,
}


ENTITY_POOL = {
    "user_101": """
    Ontology:
    北京大学本科生，女，大三，经济学院。
    喜欢摄影、旅行、日料、华语流行音乐，
    常听陈奕迅、孙燕姿，也很喜欢唱 KTV。
    性格外向，学院活动参加得比较多。
    这周六晚上 19:00 以后没有安排。
    羽毛球约 4 级，平时偶尔在邱德拔打球。

    Demand:
    最近想找人一起准备托福口语；
    想认识更多不同院系的同学；
    偶尔会约朋友唱歌。

    Supply:
    可以分享经院选课和交换项目经验；
    周末晚上通常愿意参加校内或学校附近的活动。
    """,

    "user_102": """
    Ontology:
    北京大学硕士生，男，计算机学院。
    平时主要做系统研究，喜欢健身、德州扑克、开源软件。
    不太唱歌，也很少参加 KTV。
    羽毛球约 5 级，常在五四体育中心打球。
    这周六晚上要在实验室值班。
    手上有几次体育场馆预订记录。

    Demand:
    最近在找系统方向实习；
    想找 4.5 级以上固定男双搭子；
    准备升级显卡。

    Supply:
    可以帮忙看 C++ / 系统开发问题；
    这周日有一块五四羽毛球场 19:00-21:00 可以转让。
    """,

    "user_103": """
    Ontology:
    北京大学本科生，女，大二，外国语学院。
    喜欢音乐剧、日语、桌游，也经常听华语和日语流行歌，
    尤其喜欢周杰伦、陈奕迅、孙燕姿。
    唱歌水平一般，但很喜欢朋友聚会和 KTV，
    性格比较外向。
    这周六晚上 18:30-22:30 有空。
    羽毛球约 3.5 级，双打和混双较多。

    Demand:
    想找人练日语口语；
    最近想多参加一些轻松的社交活动；
    偶尔找混双搭子。

    Supply:
    可以一起参加音乐剧、桌游或唱歌活动；
    周末下午偶尔约羽毛球。
    """,

    "user_104": """
    Ontology:
    北京大学本科生，男，大四，信息科学技术学院。
    喜欢骑行、游戏、摄影和硬件折腾。
    羽毛球水平一般，偶尔和同学打。
    最近毕业事情比较多，社交活动参加得少。
    这周六晚上在学校。
    前几天临时订了一块邱德拔羽毛球场。

    Demand:
    想收一个 4TB 机械硬盘做备份盘；
    最近在找周末骑行搭子。

    Supply:
    出 WD Black SN850X 2TB；
    这周六 19:00-21:00 的邱德拔羽毛球场临时用不上，
    原价转让，可以直接校内交接预订信息；
    可以帮忙看基础硬件装机问题。
    """,

    "no_match": "当前没有 Candidate 能够较好满足这次 Connection Request。",
}


async def select(connection_request: str):
    async with AsyncTypeSafeClient() as client:
        response = await client.system_one(
            state={
                "requester": requester,
                "connection_request": connection_request,
            },
            questions={
                "match": Choice(
                    instructions=SELECTION_INSTRUCTIONS,
                    criteria=ENTITY_POOL,
                )
            },
        )

    match = response.choices["match"]

    print("request:", connection_request)
    print("selected:", match.choice)
    print("probabilities:", match.probabilities)
    print("confidence:", match.confidence)
    print()


async def main():
    ktv_request = (
        "这周六晚上想临时找一个北大同学一起去唱 KTV，"
        "希望 19:00 以后有空，喜欢华语流行，愿意一起唱两三个小时；"
        "最好性格外向一点。"
    )

    court_transfer_request = (
        "临时想收一块这周六 19:00-21:00 的北大羽毛球场地，"
        "最好是邱德拔，必须是当天这个时间段，原价或更低都可以。"
    )

    await select(ktv_request)
    await select(court_transfer_request)


asyncio.run(main()
```
</content>
</page>
