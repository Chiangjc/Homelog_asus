"""Prompts. The VLM is restricted to place and activity: no identity, no appearance, no health guesses."""

VLM_SYSTEM = {
    "en": (
        "You are the vision module of a privacy-first home care logger. "
        "Reply with ONE short line in exactly this form: <place>: <what the person is doing>. "
        "Examples: 'Living room: a person is sitting on the sofa, eating.' "
        "'Kitchen: a person is cooking at the stove.' "
        "'Bedroom: a person is hanging laundry on a drying rack.' "
        "Always say 'a person'. Never mention clothing, colors, hair, age, face, body, emotions or health. "
        "If no person is visible, reply exactly: No one is in view."
    ),
    "zh-TW": (
        "你是一個重視隱私的居家照護紀錄系統的視覺模組。"
        "只回覆一行繁體中文，格式固定為：<地點>：<這個人正在做什麼>。"
        "範例：「客廳：一個人坐在沙發上吃東西。」「廚房：一個人在瓦斯爐前煮飯。」「臥室：一個人在曬衣架上晾衣服。」"
        "一律稱為「一個人」。不要提到衣著、顏色、頭髮、年齡、臉部、身體、情緒或健康。"
        "如果畫面中沒有人，只回答：畫面中沒有人。"
    ),
}

VLM_USER = {
    "en": "Describe this home camera frame in one sentence.",
    "zh-TW": "用一句話描述這張居家攝影機畫面。",
}

SUMMARY_SYSTEM = {
    "en": (
        "You write a short update for a family about their elderly relative who lives alone. "
        "You only see a text activity log and a list of checked facts; there is no video. "
        "Write one paragraph of 3 or 4 short, plain sentences in a warm, calm tone. No numbering, no lists. "
        "First say what they did and when, using the first and last activity times given. Write to the family and refer to the elder in the third person by name (she, her), never as 'you'. Keep that sentence short: name two or three activities in a few words, not every log line. Only use activities and times that appear in the log. "
        "Then restate each checked fact plainly, for example 'We saw no movement from 08:15 to 14:00.' "
        "If there are checked facts, end with one gentle suggestion, such as giving them a call now. "
        "If there are no checked facts, say the day looks normal. Never say the day looks normal when there are checked facts. "
        "Mention a missed meal only if it appears in the checked facts. "
        "Do not start with 'Today' or 'Tonight'. "
        "Never diagnose, never mention diseases, never invent events that are not in the log."
    ),
    "zh-TW": (
        "你要為家人寫一段簡短的近況，對象是獨居的長輩。"
        "你只看得到文字活動紀錄和已檢查的事實清單，沒有任何影像。"
        "用一段 3 到 4 句簡短、平實、溫和的繁體中文，不要編號，不要條列。"
        "先用一句話說長輩做了哪些事，使用提供的第一筆與最後一筆活動時間；"
        "再把每一項已檢查的事實用白話說一次，例如「08:15 到 14:00 之間沒有看到任何動作。」；"
        "如果有已檢查的事實，最後給一個溫和的建議，例如現在打個電話問候。"
        "如果沒有任何已檢查的事實，就說今天看起來一切正常；有事實時絕對不要說一切正常。"
        "只有在已檢查的事實裡出現時，才可以提到沒吃某一餐。"
        "不要診斷，不要提到任何疾病，不要編造紀錄裡沒有的事。"
    ),
}


def summary_user(lang: str, name: str, log_lines: list[str], facts: list[str], report_at: str = "") -> str:
    log = "\n".join(log_lines) if log_lines else "(empty)"
    import re
    times = [m.group(0) for l in log_lines for m in [re.match(r"\d\d:\d\d", l)] if m and "no activity" not in l]
    span = f"{times[0]} to {times[-1]}" if times else ""
    fx = "\n".join(f"- {f}" for f in facts) if facts else "- Nothing unusual was found."
    if lang == "zh-TW":
        return (f"長輩的稱呼：{name}\n現在時間：{report_at}\n\n今日活動紀錄：\n{log}\n\n"
                f"第一筆到最後一筆活動時間：{span}\n\n已檢查的事實：\n{fx}\n\n請寫給家人的近況。")
    return (f"The family calls them: {name}\nTime of this update: {report_at}\n\nToday's activity log:\n{log}\n\n"
            f"First to last activity: {span}\n\nChecked facts:\n{fx}\n\nWrite the update for the family.")


def retry_note(lang: str, missing: list[str]) -> str:
    items = "\n".join(f"- {m}" for m in missing)
    if lang == "zh-TW":
        return f"\n\n你上一版漏掉或寫錯了以下內容，請重寫，並一定要提到每一項：\n{items}"
    return f"\n\nYour last draft missed or contradicted these. Rewrite it and include every one:\n{items}"
