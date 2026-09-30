"""
Agent工具：基于 Neo4j 知识图谱的景点检索与路线规划
结构化约束走 Cypher，语义模糊走向量（可选），路线规划走本地计算
"""
import os
import math
import re
import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# ==================== 加载 .env ====================
# 兼容 .env 在项目根目录或当前目录两种放法
_root_env = Path(__file__).parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)
else:
    load_dotenv()

# ==================== Neo4j 连接 ====================
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
if not NEO4J_PASSWORD:
    raise RuntimeError("请在 .env 中配置 NEO4J_PASSWORD")

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def run_cypher(cypher: str, **params):
    """执行 Cypher，返回 list[dict]"""
    with get_driver().session() as session:
        result = session.run(cypher, **params)
        return [dict(r) for r in result]


# ==================== 工具函数 ====================
def _parse_lat(s):
    if not s:
        return None
    s = str(s).replace('°N', '').replace('°S', '').replace('°E', '').replace('°W', '')
    s = s.replace(' ', '').strip()
    try:
        return float(s)
    except:
        return None


def _parse_duration_min(s):
    """解析 '60分钟' -> 60；也兼容 '60' / 60"""
    if s is None:
        return 0
    if isinstance(s, (int, float)):
        return int(s)
    m = re.search(r'(\d+)', str(s))
    return int(m.group(1)) if m else 0


def haversine(lat1, lon1, lat2, lon2):
    """两点距离（公里）"""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _parse_open_range(s):
    """
    解析营业时间字符串，返回 (开门分钟, 关门分钟, 备注)
    - 普通营业时间：'9：00~17：30（周一闭馆）' → (540, 1050, '周一闭馆')
    - 全天开放：'全天开放' → (0, 1440, '')
    - 演出/活动时间：'每周六/日15:00~16:00（节假日加场）' 
      → (0, 1440, '注意：每周六/日15:00~16:00（节假日加场）')
    """
    if not s:
        return (0, 24 * 60, "")
    s = str(s).strip()
    if "全天" in s:
        return (0, 24 * 60, "")

    # ★ 关键：以"每周"、"周X"开头的，才是演出时间（不是营业时间）
    if re.match(r'^\s*(每周|周[一二三四五六日])', s):
        return (0, 24 * 60, f"注意：{s}")

    # 普通营业时间
    matches = re.findall(r'(\d{1,2})\s*[:：]\s*(\d{2})', s)
    if len(matches) < 2:
        return (0, 24 * 60, "")
    start = int(matches[0][0]) * 60 + int(matches[0][1])
    end = int(matches[1][0]) * 60 + int(matches[1][1])
    if end <= start:
        end += 24 * 60
    note_match = re.search(r'[（(]([^）)]+)[）)]', s)
    note = note_match.group(1) if note_match else ""
    return (start, end, note)


# ==================== 演出/场次解析（2026-09-26 新增） ====================
# 目的：把"每周六/日15:00~16:00"这类演出信息解析成结构化约束，供编排时按星期几判断。
_WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_CLOSED_RE = re.compile(
    r"(?:周|星期)?([一二三四五六日天])(?:\s*(?:至|到)\s*(?:周|星期)?([一二三四五六日天]))?\s*(?:闭馆|休馆|不开放|不开)"
)


def _parse_closed_days(s):
    """从字符串提取闭馆星期集合（2026-09-26 新增）：
    '周一闭馆' → {0}；'周一至周五闭馆' → {0..4}；无闭馆信息 → 空集。
    用于避免非闭馆日误提示（如周六去侨批馆不应提示'周一闭馆'）。"""
    if not s:
        return set()
    # 不含任何闭馆关键词（如'每周六/日15:00~16:00（节假日加场）'）→ 不是闭馆信息
    if not re.search(r"闭馆|休馆|不开放|不开", s):
        return set()
    m = _CLOSED_RE.search(s)
    if m:
        lo = _WEEKDAY_MAP.get(m.group(1))
        hi = _WEEKDAY_MAP.get(m.group(2)) if m.group(2) else lo
        if lo is None:
            return set()
        if hi is None or hi >= lo:
            return {(i % 7) for i in range(lo, (hi if hi is not None else lo) + 1)}
        return {lo, hi}
    # 兜底：'每周一' / '周一、周三' 等散列写法
    return {_WEEKDAY_MAP[ch] for ch in re.findall(r"[一二三四五六日天]", s) if ch in _WEEKDAY_MAP}


def _parse_performances(s):
    """
    解析演出/活动场次字符串 → [(weekdays集合, 开始分钟, 结束分钟, 原始备注)]
    weekdays 与 datetime.weekday() 对齐（0=周一 ... 6=周日）。
    支持：'每周六/日15:00~16:00（节假日加场）' / '周六、周日 15:00-16:00' / '周一至周五10:00-11:00'
    解析不出返回 []（调用方按无演出处理）。
    """
    if not s:
        return []
    s = str(s).strip()
    if not re.match(r'^(每周|周[一二三四五六日天]|星期[一二三四五六日天])', s):
        return []
    m = re.search(r'(\d{1,2})\s*[:：]\s*(\d{2})\s*[~至\-]\s*(\d{1,2})\s*[:：]\s*(\d{2})', s)
    if not m:
        return []
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    weekdays = set()
    # 范围写法：'周一至周五' → {0..4}；否则收集所有星期字：'周六、周日'/'每周六/日' → {5,6}
    m_range = re.search(r'(?:周|星期)?([一二三四五六日天])\s*(?:至|到)\s*(?:周|星期)?([一二三四五六日天])', s)
    if m_range:
        lo, hi = _WEEKDAY_MAP[m_range.group(1)], _WEEKDAY_MAP[m_range.group(2)]
        weekdays = {(i % 7) for i in range(lo, hi + 1)}
    else:
        weekdays = {_WEEKDAY_MAP[ch] for ch in s if ch in _WEEKDAY_MAP}
    return [(weekdays, start, end, s)] if weekdays else []


def _fmt_weekdays(weekdays):
    """{5,6} → '周六/周日'（按周一到周日顺序输出）"""
    names = [_WEEKDAY_NAMES[i] for i in sorted(weekdays)]
    return "/".join(names)


def _apply_constraints(arrive, spot, day_of_week):
    """
    对单个景点的到达时间应用约束，返回 (调整后arrive, leave, warnings, today_unavailable)：
    1) 开放窗口：到达早于开门 → 顺延到开门时间（保留 warning 兜底）
    2) 演出场次：传入 day_of_week 时，演出日 → 顺延到演出开始时间；非演出日 → warning + today_unavailable=True
       （today_unavailable 供 LLM 明确判断"今天不该硬排"，不依赖 LLM 自行推理）
    """
    duration = spot["duration"]
    open_min, close_min, note = _parse_open_range(spot.get("opening_hours", ""))
    warnings = []
    unavailable = False
    if open_min > 0 and arrive < open_min:
        arrive = open_min
    if day_of_week is not None:
        for wdays, p_start, p_end, p_note in _parse_performances(spot.get("opening_hours", "")):
            if day_of_week in wdays:
                if arrive < p_start:
                    arrive = p_start
            else:
                warnings.append(f"演出仅在{_fmt_weekdays(wdays)}有，今日{_WEEKDAY_NAMES[day_of_week]}无演出，不建议硬排")
                unavailable = True
    leave = arrive + duration
    if note:
        # 闭馆 note（如'周一闭馆'）只在当天是闭馆日时提示；其他 note（演出加场等）保留原样
        closed = _parse_closed_days(note)
        if closed:
            if day_of_week is not None and day_of_week in closed:
                warnings.append("今日闭馆，不可安排")
                unavailable = True
            elif day_of_week is None:
                warnings.append(note)
        else:
            warnings.append(note)
    if open_min > 0 and arrive < open_min:
        warnings.append(f"{_minutes_to_hhmm(open_min)} 才开门，到达太早")
    if close_min < 24 * 60 and leave > close_min:
        warnings.append(f"{_minutes_to_hhmm(close_min)} 就关门，可能来不及")
    return arrive, leave, warnings, unavailable


def _minutes_to_hhmm(minutes):
    """分钟数转 'HH:MM'，如 510 → '08:30'"""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def _transfer_minutes(dist_km):
    """根据距离估算交通时间（分钟）"""
    if dist_km < 0.5:
        return 5
    elif dist_km < 2:
        return 10
    elif dist_km < 5:
        return 20
    else:
        return 30


# ==================== 工具 1：图谱结构化查询 ====================
def search_spots_by_graph(theme_name=None, group_name=None,
                          district=None, max_duration=None, limit=20):
    """
    基于图谱的关系查询：主题 → 活动 → 资源，可叠加人群、区域、时长
    """
    cypher = """
    MATCH (r)-[:包含活动]->(a:StudyActivity)
    """
    params = {"limit": limit}

    if theme_name:
        cypher += """
        MATCH (a)-[:适配主题]->(t:StudyTheme)
        WHERE t.name CONTAINS $theme
        """
        params["theme"] = theme_name

    if group_name:
        cypher += """
        MATCH (a)-[:适合人群]->(g:TargetGroup)
        WHERE g.group_name CONTAINS $group
        """
        params["group"] = group_name

    if district:
        cypher += " AND r.district CONTAINS $district"
        params["district"] = district

    if max_duration:
        cypher += " AND a.suitable_duration <= $maxdur"
        params["maxdur"] = max_duration

    cypher += """
    RETURN DISTINCT
        r.name AS resource,
        r.district AS district,
        r.latitude AS lat,
        r.longitude AS lon,
        a.name AS activity,
        a.suitable_duration AS duration
    LIMIT $limit
    """

    return run_cypher(cypher, **params)


# ==================== 工具 2：语义检索（可选）====================
def search_spots_by_vector(query: str, top_k: int = 10):
    """
    语义检索：需节点有 embedding 属性和向量索引。
    没有时降级为关键词模糊匹配（不报错）。
    """
    try:
        from openai import OpenAI
        client = OpenAI()
        emb = client.embeddings.create(
            model="text-embedding-3-small", input=query
        ).data[0].embedding

        cypher = """
        CALL db.index.vector.queryNodes('resource_embeddings', $k, $emb)
        YIELD node, score
        RETURN node.name AS name,
               node.district AS district,
               node.description AS description,
               node.latitude AS lat,
               node.longitude AS lon,
               score
        """
        return run_cypher(cypher, k=top_k, emb=emb)
    except Exception:
        cypher = """
        MATCH (n)
        WHERE (n:CoreResource OR n:IntangibleResource OR n:TourismResource)
          AND (n.name CONTAINS $q OR n.description CONTAINS $q)
        RETURN n.name AS name, n.district AS district,
               n.description AS description,
               n.latitude AS lat, n.longitude AS lon,
               0.5 AS score
        LIMIT $k
        """
        return run_cypher(cypher, q=query, k=top_k)


# ==================== 工具 3：景点详情 ====================
def get_spot_detail(name):
    """查询单个景点详情（跨 CoreResource / IntangibleResource / TourismResource）"""
    cypher = """
    MATCH (n)
    WHERE (n:CoreResource OR n:IntangibleResource OR n:TourismResource)
      AND (n.name CONTAINS $name OR $name CONTAINS n.name)
    RETURN n.name AS name,
           n.district AS district,
           n.activity_duration AS duration,
           n.opening_hours AS opening_hours,
           n.description AS description,
           n.capacity AS capacity,
           n.latitude AS latitude,
           n.longitude AS longitude
    LIMIT 1
    """
    rows = run_cypher(cypher, name=name)
    return rows[0] if rows else None


# ==================== 工具 4：路线规划（本地计算）====================
def _schedule_spots(spots, day_of_week=None, day_start=8 * 60 + 30, day_cap=480):
    """
    纯编排函数（不查库，可独立单测）：
    贪心按距离排序 → 按天切分 → 开放窗口/演出场次约束（_apply_constraints）→ 生成时间块与 warning。
    day_of_week: 0=周一 ... 6=周日；None 表示不校验演出场次。
    改动记录(2026-09-26)：原 plan_route 内联逻辑抽出，新增"到达早于开门自动顺延"与"演出场次按星期几校验"。
    """
    if not spots:
        return {"total_distance_km": 0, "estimated_days": 0, "route": []}

    # 贪心 TSP（按距离；单景点保持原序）
    # 排序策略：有演出场次的景点排序列末尾——演出多在下午/晚间，
    # 若演出景点在序列头部，顺延到演出开始会把后续景点全部挤到第二天。
    if len(spots) > 1:
        perf_ids = {id(s) for s in spots if _parse_performances(s.get("opening_hours", ""))}
        perf = [s for s in spots if id(s) in perf_ids]
        norm = [s for s in spots if id(s) not in perf_ids]
        pool = norm if norm else spots
        ordered = [pool[0]]
        remaining = pool[1:]
        total_dist = 0
        while remaining:
            last = ordered[-1]
            nearest_idx = min(
                range(len(remaining)),
                key=lambda i: haversine(last["lat"], last["lon"],
                                        remaining[i]["lat"], remaining[i]["lon"])
            )
            nxt = remaining.pop(nearest_idx)
            total_dist += haversine(last["lat"], last["lon"], nxt["lat"], nxt["lon"])
            ordered.append(nxt)
        if perf and norm:
            # 演出景点接到末尾（保持原相对顺序），距离纳入总里程
            # 注意：norm 为空时 perf 已含在贪心结果中，不再追加（避免重复）
            for i, p in enumerate(perf):
                if ordered:
                    total_dist += haversine(ordered[-1]["lat"], ordered[-1]["lon"],
                                            p["lat"], p["lon"])
                ordered.append(p)
    else:
        ordered = list(spots)
        total_dist = 0

    route = []
    current_day = []
    current_time = day_start
    day_start_time = day_start
    day_num = 1

    for spot in ordered:
        arrive, leave, warnings, unavailable = _apply_constraints(current_time, spot, day_of_week)

        # 跨天判断（用约束后的 leave 判断）
        if (leave - day_start_time) > day_cap and current_day:
            route.append({
                "day": day_num,
                "spots": current_day,
                "total_visit_minutes": sum(s["duration"] for s in current_day),
            })
            day_num += 1
            current_day = []
            current_time = day_start
            day_start_time = day_start
            arrive, leave, warnings, unavailable = _apply_constraints(day_start, spot, day_of_week)

        spot["arrive_time"] = _minutes_to_hhmm(arrive)
        spot["leave_time"] = _minutes_to_hhmm(leave)
        spot["time_warning"] = "；".join(warnings) if warnings else None
        spot["today_unavailable"] = unavailable
        current_day.append(spot)

        # 根据到下一个景点的实际距离估算交通时间
        idx = ordered.index(spot)
        if idx + 1 < len(ordered):
            next_spot = ordered[idx + 1]
            dist_to_next = haversine(spot["lat"], spot["lon"],
                                     next_spot["lat"], next_spot["lon"])
            current_time = leave + _transfer_minutes(dist_to_next)
        else:
            current_time = leave

    # 收尾最后一天
    if current_day:
        route.append({
            "day": day_num,
            "spots": current_day,
            "total_visit_minutes": sum(s["duration"] for s in current_day),
        })

    return {
        "total_distance_km": round(total_dist, 1),
        "estimated_days": len(route),
        "route": route,
    }


def plan_route(spot_names, days=1, day_of_week=None):
    """
    给定景点列表，按距离贪心排序，分配到 days 天。
    每天从 08:30 开始，每个景点带 arrive_time / leave_time，
    并根据 opening_hours 自动生成 time_warning。
    day_of_week（0=周一...6=周日）由服务端注入，用于演出场次校验：演出日顺延到演出开始、非演出日提示不要硬排。
    """
    cypher = """
    MATCH (n)
    WHERE (n:CoreResource OR n:IntangibleResource OR n:TourismResource)
    AND ANY(input_name IN $names 
            WHERE n.name CONTAINS input_name OR input_name CONTAINS n.name)
    RETURN DISTINCT n.name AS name,
        n.latitude AS lat_raw,
        n.longitude AS lon_raw,
        n.activity_duration AS duration_raw,
        n.opening_hours AS opening_hours,
        n.description AS description
    """
    rows = run_cypher(cypher, names=spot_names)

    spots = []
    for r in rows:
        lat = _parse_lat(r.get("lat_raw"))
        lon = _parse_lat(r.get("lon_raw"))
        if lat is None or lon is None:
            continue
        spots.append({
            "name": r["name"],
            "lat": lat,
            "lon": lon,
            "duration": _parse_duration_min(r.get("duration_raw")) or 60,
            "opening_hours": r.get("opening_hours", ""),
            "description": (r.get("description") or "")[:100],
        })

    return _schedule_spots(spots, day_of_week=day_of_week)


# ==================== 工具 5：邻近推荐（图谱优先）====================
def nearby_recommend(name: str, radius_km: float = 3, limit: int = 5):
    center = get_spot_detail(name)
    if not center:
        return []
    clat = _parse_lat(center.get("latitude"))
    clon = _parse_lat(center.get("longitude"))
    if clat is None or clon is None:
        return []

    cypher = """
    MATCH (r)-[:邻近]-(near)
    WHERE r.name CONTAINS $name OR $name CONTAINS r.name
    RETURN DISTINCT near.name AS name,
           near.district AS district,
           near.activity_duration AS duration,
           near.opening_hours AS opening_hours,
           near.latitude AS lat_raw,
           near.longitude AS lon_raw
    """
    rows = run_cypher(cypher, name=name)

    results = []
    for r in rows:
        lat = _parse_lat(r.get("lat_raw"))
        lon = _parse_lat(r.get("lon_raw"))
        if lat is None or lon is None:
            continue
        dist = haversine(clat, clon, lat, lon)
        if dist <= radius_km:
            results.append({
                "name": r["name"],
                "distance_km": round(dist, 2),
                "district": r.get("district", ""),
                "duration": r.get("duration", ""),
                "opening_hours": r.get("opening_hours", ""),
            })
    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


# ==================== 工具 6：联网搜索 ====================
def web_search(query):
    """用 Tavily 联网搜索"""
    try:
        from tavily import TavilyClient
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return {"error": "未配置 TAVILY_API_KEY"}
        client = TavilyClient(api_key=api_key)
        result = client.search(query, max_results=3)
        return [
            {"title": r["title"], "content": r["content"][:200], "url": r["url"]}
            for r in result.get("results", [])
        ]
    except Exception as e:
        return {"error": str(e)}


# ==================== 工具 Schema（给 LLM）====================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_spots_by_graph",
            "description": "基于知识图谱查询景点，支持结构化约束。适合有明确条件的查询，如'适合亲子的非遗活动''金平区的历史景点'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme_name": {
                        "type": "string",
                        "description": "研学主题，如'非遗民俗''城市记忆''红色基因''海上侨乡''文化传承''乡村侨史''侨乡饮食'"
                    },
                    "group_name": {
                        "type": "string",
                        "description": "目标人群，如'亲子''学子''手作爱好者''民俗爱好者''文旅爱好者''戏迷''乐迷''研究者''医趣者'"
                    },
                    "district": {
                        "type": "string",
                        "description": "区域，如'金平区''龙湖区''澄海区''濠江区''潮阳区''潮南区''南澳县'"
                    },
                    "max_duration": {
                        "type": "integer",
                        "description": "单个活动最长时长（分钟），如 60"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_spots_by_vector",
            "description": "语义检索景点。适合模糊描述，如'有侨乡味道的地方''红色景点''能体验手工的场所'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言查询"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_spot_detail",
            "description": "查询某个景点的详细信息：开放时间、地址、描述、容纳人数、经纬度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "景点名称，如'小公园''侨批文物馆'"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_route",
            "description": "给定景点名称列表，按地理位置贪心排序，自动分配到多天，返回最优游览路线。返回值里每个景点都带 arrive_time / leave_time / time_warning，请严格遵守这些时间字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "spot_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "景点名称列表"
                    },
                    "days": {"type": "integer", "description": "计划游玩天数"}
                },
                "required": ["spot_names", "days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "nearby_recommend",
            "description": "推荐某个景点附近的景点。优先用知识图谱的邻近关系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "中心景点名称"},
                    "radius_km": {"type": "number", "description": "搜索半径（公里），默认 3"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索最新信息，如天气、门票、最新活动。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如'汕头明天天气'"}
                },
                "required": ["query"]
            }
        }
    }
]


# ==================== 工具名 → 函数映射 ====================
def _plan_route_with_context(**kwargs):
    """包装 plan_route：服务端自动注入真实星期几（0=周一...6=周日），LLM 无需感知"""
    return plan_route(
        spot_names=kwargs.get("spot_names") or [],
        days=kwargs.get("days") or 1,
        day_of_week=datetime.date.today().weekday(),
    )


TOOL_FUNCTIONS = {
    "search_spots_by_graph": search_spots_by_graph,
    "search_spots_by_vector": search_spots_by_vector,
    "get_spot_detail": get_spot_detail,
    "plan_route": _plan_route_with_context,
    "nearby_recommend": nearby_recommend,
    "web_search": web_search,
}