"""Conservative, target-bound Douyin restriction evidence for reversible archiving."""
from copy import deepcopy

PROFILE_SOURCE = "douyin_profile_other"


def confirmed_douyin_restriction(profile, sec_user_id, diagnostic):
    """Require a successful full-profile response, never a name or empty list.

    Deleted profiles may omit sec_uid. Accept that platform tombstone only with
    both user_deleted and the explicit deletion title/content, bound to the
    requested sec_user_id by the collector. A conflicting ID is always rejected.
    Numeric ban_type is deliberately not used: mute and follow restrictions can
    share the same value.
    """
    if not isinstance(profile, dict) or not isinstance(diagnostic, dict) or not sec_user_id:
        return None
    if (diagnostic.get("api_status") != 0
            or diagnostic.get("http_status") not in (None, 200)
            or diagnostic.get("error_type") or diagnostic.get("_error")):
        return None
    returned_id = str(profile.get("sec_uid") or "")
    if returned_id and returned_id != sec_user_id:
        return None
    special = profile.get("special_state_info")
    special = special if isinstance(special, dict) else {}
    title = str(special.get("title") or "")
    content = str(special.get("content") or "")
    state = ""
    reason = ""
    if (profile.get("user_deleted") is True
            and title in {"账号已经注销", "账号已注销", "用户已注销"}
            and "注销" in content):
        state, reason = "deleted", content
    elif returned_id == sec_user_id and profile.get("uid"):
        punishment = profile.get("punish_remind_info")
        punishment = punishment if isinstance(punishment, dict) else {}
        if profile.get("is_ban") is not True and punishment.get("is_punish") is not True:
            return None
        messages = []
        for key in ("prompt_bar", "punish_content"):
            value = punishment.get(key)
            if isinstance(value, dict) and isinstance(value.get("content"), str):
                messages.append(value["content"])
        text = "；".join(dict.fromkeys(messages))
        if "被禁言" in text:
            state = "muted"
        elif "被禁止关注" in text:
            state = "follow_restricted"
        elif any(term in text for term in ("被封禁", "账号已封禁", "帐号已封禁")):
            state = "banned"
        reason = text
    if not state:
        return None
    # Persist only state evidence, not credentials, request headers or URLs.
    evidence = {key: deepcopy(profile[key]) for key in (
        "uid", "sec_uid", "user_deleted", "is_ban", "special_state_info",
    ) if key in profile}
    punishment = profile.get("punish_remind_info")
    if isinstance(punishment, dict):
        evidence["punish_remind_info"] = {
            key: deepcopy(punishment[key]) for key in ("is_punish", "ban_type") if key in punishment
        }
        for key in ("prompt_bar", "punish_content"):
            value = punishment.get(key)
            if isinstance(value, dict):
                evidence["punish_remind_info"][key] = {"content": str(value.get("content") or "")[:500]}
    if isinstance(evidence.get("special_state_info"), dict):
        evidence["special_state_info"] = {
            key: evidence["special_state_info"][key]
            for key in ("title", "content", "special_state") if key in evidence["special_state_info"]
        }
    return {"source": PROFILE_SOURCE, "state": state, "target_sec_uid": sec_user_id,
            "reason": reason[:300], "api_status": 0, "evidence": evidence}


def validate_archive_evidence(value, sec_user_id):
    if (not isinstance(value, dict) or value.get("source") != PROFILE_SOURCE
            or value.get("target_sec_uid") != sec_user_id):
        return None
    return confirmed_douyin_restriction(value.get("evidence"), sec_user_id,
                                       {"api_status": value.get("api_status")})
