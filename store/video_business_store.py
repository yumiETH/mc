# -*- coding: utf-8 -*-

import json
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import VideoAccount, VideoDetail
from tools import utils


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalize_url(value: Any) -> Optional[str]:
    url = _to_str(value)
    if not url:
        return None

    url = url.strip()
    parsed_url = urlsplit(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return url

    normalized_path = parsed_url.path.rstrip("/")
    return urlunsplit((parsed_url.scheme, parsed_url.netloc, normalized_path, "", ""))


def _now() -> datetime:
    return datetime.now()


def _account_url(platform: str, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    if platform == "dy":
        return f"https://www.douyin.com/user/{user_id}"
    if platform == "bili":
        return f"https://space.bilibili.com/{user_id}"
    if platform == "ks":
        return f"https://www.kuaishou.com/profile/{user_id}"
    if platform == "wb":
        return f"https://m.weibo.cn/u/{user_id}"
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{user_id}"
    return None


def _content_id(content_item: Dict, platform: str) -> Optional[str]:
    return _to_str(
        _first_value(
            content_item.get("aweme_id"),
            content_item.get("video_id"),
            content_item.get("note_id"),
            content_item.get("content_id"),
        )
    )


def _user_id(item: Dict, platform: Optional[str] = None) -> Optional[str]:
    if platform == "dy":
        return _to_str(_first_value(item.get("sec_uid"), item.get("user_id"), item.get("third_user_id")))
    return _to_str(_first_value(item.get("user_id"), item.get("third_user_id")))


def _map_account(platform: str, item: Dict) -> Dict[str, Any]:
    user_id = _user_id(item, platform)
    user_url = _normalize_url(
        _first_value(
            item.get("user_url"),
            item.get("user_link"),
            item.get("profile_url"),
            item.get("url"),
            _account_url(platform, user_id),
        )
    )
    return {
        "nick_name": _first_value(
            item.get("nickname"),
            item.get("nick_name"),
            item.get("user_nickname"),
            item.get("user_name"),
        ),
        "url": user_url,
        "ip_location": item.get("ip_location"),
        "total_favorited": _to_int(_first_value(item.get("total_favorited"), item.get("interaction"), item.get("total_liked")), 0),
        "short_id": _first_value(item.get("short_user_id"), item.get("user_unique_id"), item.get("short_id")),
        "following_count": _to_int(_first_value(item.get("following_count"), item.get("follows")), 0),
        "mplatform_followers_count": _to_int(_first_value(item.get("mplatform_followers_count"), item.get("fans"), item.get("total_fans")), 0),
        "user_age": _to_int(item.get("user_age"), 0),
        "signature": _first_value(item.get("user_signature"), item.get("signature"), item.get("desc"), item.get("sign")),
        "third_user_id": user_id,
        "avatar": _first_value(item.get("avatar"), item.get("user_avatar")),
        "aweme_count": _to_int(_first_value(item.get("aweme_count"), item.get("videos_count")), 0),
        "update_time": _now(),
        "del_flag": "0",
        "tenant_id": item.get("tenant_id", "000000"),
        "type": platform,
    }


def _map_detail(platform: str, item: Dict, account_id: Optional[int]) -> Dict[str, Any]:
    content_id = _content_id(item, platform)
    digg_count = _first_value(item.get("liked_count"), item.get("digg_count"))
    collect_count = _first_value(item.get("collected_count"), item.get("collect_count"), item.get("video_favorite_count"))
    comment_count = _first_value(item.get("comment_count"), item.get("comments_count"), item.get("video_comment"))
    share_count = _first_value(item.get("share_count"), item.get("shared_count"), item.get("video_share_count"))
    view_count = _first_value(item.get("view_count"), item.get("viewd_count"), item.get("video_play_count"))
    user_id = _user_id(item, platform)

    return {
        "account_id": account_id,
        "aweme_id": content_id,
        "title": (_first_value(item.get("title"), item.get("desc"), item.get("content")) or "")[:255],
        "nick_name": _first_value(item.get("nickname"), item.get("user_nickname"), item.get("user_name"), item.get("nick_name")),
        "video_cover": _first_value(item.get("cover_url"), item.get("video_cover_url")),
        "work_type": _first_value(item.get("aweme_type"), item.get("video_type"), item.get("type")),
        "admire_count": _to_int(item.get("admire_count"), 0),
        "digg_count": _to_int(digg_count, 0),
        "comment_count": _to_int(comment_count, 0),
        "collect_count": _to_int(collect_count, 0),
        "share_count": _to_int(share_count, 0),
        "view_count": _to_int(view_count, 0),
        "duration": _to_str(item.get("duration")),
        "topics": _to_str(_first_value(item.get("tag_list"), item.get("topics"))),
        "video_create_time": _to_str(_first_value(item.get("create_time"), item.get("time"), item.get("publish_time"))),
        "video_addr": _first_value(item.get("video_download_url"), item.get("video_play_url"), item.get("video_url"), item.get("aweme_url"), item.get("note_url")),
        "images": _first_value(item.get("note_download_url"), item.get("image_list"), item.get("images")),
        "user_url": _normalize_url(
            _first_value(
                item.get("user_url"),
                item.get("user_link"),
                item.get("profile_url"),
                item.get("url"),
                _account_url(platform, user_id),
            )
        ),
        "author_avatar": _first_value(item.get("avatar"), item.get("user_avatar")),
        "following_count": _to_int(_first_value(item.get("following_count"), item.get("follows")), 0),
        "follower_count": _to_int(_first_value(item.get("follower_count"), item.get("fans"), item.get("total_fans")), 0),
        "total_favorited": _to_int(_first_value(item.get("total_favorited"), item.get("interaction"), item.get("total_liked")), 0),
        "aweme_count": _to_int(_first_value(item.get("aweme_count"), item.get("videos_count")), 0),
        "tenant_id": item.get("tenant_id", "000000"),
        "del_flag": "0",
        "update_time": _now(),
        "type": platform,
    }


async def _get_existing_account(session: AsyncSession, account_data: Dict[str, Any], user_id: Optional[str]) -> Optional[VideoAccount]:
    account_type = account_data.get("type")
    user_url = account_data.get("url")
    if user_url:
        result = await session.execute(
            select(VideoAccount).where(
                VideoAccount.url == user_url,
                VideoAccount.type == account_type,
            )
        )
        account = result.scalars().first()
        if account:
            return account

    if user_id:
        result = await session.execute(
            select(VideoAccount).where(
                VideoAccount.third_user_id == user_id,
                VideoAccount.type == account_type,
            )
        )
        return result.scalars().first()

    return None


async def upsert_video_account(session: AsyncSession, platform: str, item: Dict) -> Optional[VideoAccount]:
    user_id = _user_id(item, platform)
    account_data = _map_account(platform, item)
    if not account_data.get("url") and not user_id:
        return None

    account = await _get_existing_account(session, account_data, user_id)

    if not account:
        account_data["create_time"] = _now()
        account = VideoAccount(**account_data)
        session.add(account)
        await session.flush()
        return account

    for key, value in account_data.items():
        setattr(account, key, value)
    return account


async def upsert_video_detail(session: AsyncSession, platform: str, item: Dict) -> None:
    content_id = _content_id(item, platform)
    if not content_id:
        return

    account = await upsert_video_account(session, platform, item)
    account_id = account.id if account else None
    detail_data = _map_detail(platform, item, account_id)

    stmt = select(VideoDetail).where(VideoDetail.aweme_id == content_id, VideoDetail.type == platform)
    result = await session.execute(stmt)
    detail = result.scalars().first()

    if not detail:
        detail_data["create_time"] = _now()
        detail = VideoDetail(**detail_data)
        session.add(detail)
        return

    for key, value in detail_data.items():
        setattr(detail, key, value)


async def store_video_content(session: AsyncSession, platform: str, content_item: Dict) -> None:
    await upsert_video_detail(session, platform, content_item)
    utils.logger.info(
        f"[video_business_store.store_video_content] saved platform={platform}, content_id={_content_id(content_item, platform)}"
    )


async def store_video_creator(session: AsyncSession, platform: str, creator_item: Dict) -> None:
    account = await upsert_video_account(session, platform, creator_item)
    utils.logger.info(
        f"[video_business_store.store_video_creator] saved platform={platform}, "
        f"account_id={account.id if account else None}"
    )
