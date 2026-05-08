# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/xhs/_store_impl.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

# @Author  : persist1@126.com
# @Time    : 2025/9/5 19:34
# @Desc    : Xiaohongshu storage implementation class
import json
import os
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import XhsNoteComment
from store.video_business_store import store_video_content, store_video_creator

from tools.async_file_writer import AsyncFileWriter
from tools.time_util import get_current_timestamp
from var import crawler_type_var
from database.mongodb_store_base import MongoDBStoreBase
from tools import utils
from store.excel_store_base import ExcelStoreBase

class XhsCsvStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="xhs", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        store content data to csv file
        :param content_item:
        :return:
        """
        await self.writer.write_to_csv(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        store comment data to csv file
        :param comment_item:
        :return:
        """
        await self.writer.write_to_csv(item_type="comments", item=comment_item)


    async def store_creator(self, creator_item: Dict):
        pass

    def flush(self):
        pass


class XhsJsonStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="xhs", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        store content data to json file
        :param content_item:
        :return:
        """
        await self.writer.write_single_item_to_json(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        store comment data to json file
        :param comment_item:
        :return:
        """
        await self.writer.write_single_item_to_json(item_type="comments", item=comment_item)

    async def store_creator(self, creator_item: Dict):
        pass

    def flush(self):
        """
        flush data to json file
        :return:
        """
        pass



class XhsJsonlStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="xhs", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        await self.writer.write_to_jsonl(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        await self.writer.write_to_jsonl(item_type="comments", item=comment_item)

    async def store_creator(self, creator_item: Dict):
        pass

    def flush(self):
        pass


class XhsDbStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def store_content(self, content_item: Dict):
        async with get_session() as session:
            await store_video_content(session, "xhs", content_item)

    async def store_comment(self, comment_item: Dict):
        return

    async def store_creator(self, creator_item: Dict):
        async with get_session() as session:
            await store_video_creator(session, "xhs", creator_item)

class XhsSqliteStoreImplement(XhsDbStoreImplement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class XhsMongoStoreImplement(AbstractStore):
    """Xiaohongshu MongoDB storage implementation"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mongo_store = MongoDBStoreBase(collection_prefix="xhs")

    async def store_content(self, content_item: Dict):
        """
        Store note content to MongoDB
        Args:
            content_item: Note content data
        """
        note_id = content_item.get("note_id")
        if not note_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="contents",
            query={"note_id": note_id},
            data=content_item
        )
        utils.logger.info(f"[XhsMongoStoreImplement.store_content] Saved note {note_id} to MongoDB")

    async def store_comment(self, comment_item: Dict):
        """
        Store comment to MongoDB
        Args:
            comment_item: Comment data
        """
        comment_id = comment_item.get("comment_id")
        if not comment_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="comments",
            query={"comment_id": comment_id},
            data=comment_item
        )
        utils.logger.info(f"[XhsMongoStoreImplement.store_comment] Saved comment {comment_id} to MongoDB")

    async def store_creator(self, creator_item: Dict):
        """
        Store creator information to MongoDB
        Args:
            creator_item: Creator data
        """
        user_id = creator_item.get("user_id")
        if not user_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="creators",
            query={"user_id": user_id},
            data=creator_item
        )
        utils.logger.info(f"[XhsMongoStoreImplement.store_creator] Saved creator {user_id} to MongoDB")


class XhsExcelStoreImplement:
    """Xiaohongshu Excel storage implementation - Global singleton"""

    def __new__(cls, *args, **kwargs):
        from store.excel_store_base import ExcelStoreBase
        return ExcelStoreBase.get_instance(
            platform="xhs",
            crawler_type=crawler_type_var.get()
        )
