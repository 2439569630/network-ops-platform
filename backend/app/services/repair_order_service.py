
import json
from datetime import datetime
from typing import List, Optional, Dict
from app.core.database import db
from app.constants.user import DELETED_USER_DISPLAY_NAME
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, OrderReviewCreate

# ORM Imports
from app.models.orm.repair import RepairOrder, OrderLog, OrderReview, WorkLog, RepairImage
from app.models.orm.user import User
from app.models.orm.device import NetworkDevice
from app.models.orm.location import LocationNode
from app.models.orm.rbac import Role, UserRole
from tortoise.expressions import Q
from app.services.image_storage_service import ImageStorageService

class RepairOrderService:
    """
    工单服务类
    处理报修工单的创建、指派、流转、评论等业务逻辑。
    """
    @staticmethod
    async def pick_auto_assignee_id() -> Optional[int]:
        """
        自动分配工单给运维人员
        算法：
        1. 获取 'yunwei' 角色
        2. 获取该角色的所有活跃用户
        3. 统计每个用户当前 'processing' 状态的工单数
        4. 选择负载最小的用户
        """
        # 1. Find role 'yunwei'
        role = await Role.filter(code='yunwei').first()
        if not role:
            return None
            
        # 2. Find users in that role
        urs = await UserRole.filter(role_id=role.id).all()
        user_ids = [ur.user_id for ur in urs]
        
        if not user_ids:
            return None
            
        # 3. Filter active users
        users = await User.filter(id__in=user_ids, is_approved=True).all()
        
        if not users:
            return None
            
        # 4. Count processing orders for each user
        # We can do this in loop or group by query. Loop is simple enough.
        candidates = []
        for u in users:
            count = await RepairOrder.filter(assignee_id=u.id, status='processing').count()
            candidates.append((u, count))
            
        # 5. Sort by count ASC, then ID ASC
        candidates.sort(key=lambda x: (x[1], x[0].id))
        
        return candidates[0][0].id

    @staticmethod
    async def list_assignees() -> List[dict]:
        """
        获取可选的工单处理人 (运维人员列表)
        """
        role = await Role.filter(code='yunwei').first()
        if not role:
            return []
            
        urs = await UserRole.filter(role_id=role.id).all()
        user_ids = [ur.user_id for ur in urs]
        
        users = await User.filter(id__in=user_ids, is_approved=True).order_by("id").all()
        
        return [{"id": u.id, "username": u.username} for u in users]

    @staticmethod
    async def create_order(data: RepairOrderCreate, submitter_id: int) -> int:
        """
        创建工单
        """
        # Auto-detect location if device_id is provided but location_id is not
        from app.models.orm.location import LocationNodeDevice, LocationNodeUser
        
        location_id = data.location_id
        if not location_id and data.device_id:
            loc_dev = await LocationNodeDevice.filter(device_id=data.device_id).first()
            if loc_dev:
                location_id = loc_dev.node_id
                
        # Auto-assign if location has bound users (administrators)
        assignee_id = None
        auto_assigned_reason = ""
        
        if location_id:
            # Check if any user is bound to this location
            # We pick the first one as the responsible admin
            loc_users = await LocationNodeUser.filter(node_id=location_id).order_by("id").all()
            candidate_user_ids: list[int] = []
            for r in loc_users or []:
                try:
                    candidate_user_ids.append(int(r.user_id))
                except Exception:
                    continue
            if candidate_user_ids:
                active_ids = await User.filter(
                    id__in=candidate_user_ids, is_approved=True, is_deleted=False
                ).values_list("id", flat=True)
                active_set = {int(x) for x in (active_ids or []) if x is not None}
                for r in loc_users or []:
                    try:
                        uid = int(r.user_id)
                    except Exception:
                        continue
                    if uid in active_set:
                        assignee_id = uid
                        auto_assigned_reason = "自动派单给区域管理员"
                        break
        
        order = await RepairOrder.create(
            title=data.title,
            description=data.description,
            submitter_id=submitter_id,
            device_id=data.device_id,
            location_id=location_id, # Use detected or provided location_id
            assignee_id=assignee_id,
            priority=data.priority,
            status='pending'
        )
        
        # Log creation
        log_msg = "创建工单"
        if assignee_id:
            log_msg += f" ({auto_assigned_reason})"
            
        await RepairOrderService.log_action(order.id, submitter_id, "create", "", "pending", log_msg)
        
        # 自动派单通知
        if assignee_id:
            from app.services.notification_service import NotificationService
            import logging
            try:
                await NotificationService.notify_repair_order_assigned(
                    order_id=order.id,
                    title=order.title,
                    assignee_id=assignee_id,
                    priority=order.priority,
                    reason="自动派单 (区域管理员)"
                )
            except Exception as e:
                logging.getLogger(__name__).error(f"发送自动派单通知失败: {e}")

        return order.id

    @staticmethod
    async def get_order_list(
        page: int = 1, 
        page_size: int = 10, 
        status: Optional[str] = None, 
        user_id: Optional[int] = None,
        scope: Optional[str] = None,
        # New permission flags
        can_view_all: bool = False,
        can_view_assigned: bool = False,
        role_level: int = 2,  # Deprecated
    ) -> Dict:
        """
        获取工单列表
        支持分页、状态过滤、权限控制 (个人/所有/指派)
        """
        offset = (page - 1) * page_size
        
        query = RepairOrder.all()
        
        if status:
            query = query.filter(status=status)
            
        if scope == 'personal':
            # Force personal view: Created by me OR Assigned to me
            if user_id:
                query = query.filter(Q(submitter_id=user_id) | Q(assignee_id=user_id))
        elif scope == 'created_by_me':
            if user_id:
                query = query.filter(submitter_id=user_id)
        elif scope == 'assigned_to_me':
            if user_id:
                if status == 'pending':
                    query = query.filter(Q(assignee_id=user_id) | Q(assignee_id__isnull=True))
                elif status:
                    query = query.filter(assignee_id=user_id)
                else:
                    # Default: Active orders (pending or processing)
                    # 1. Assigned to me AND not completed/closed/cancelled
                    # 2. OR Pending AND Unassigned (Public pool)
                    query = query.filter(
                        Q(assignee_id=user_id, status__in=['pending', 'processing']) | 
                        Q(status='pending', assignee_id__isnull=True)
                    )
        else:
            # Permission based filtering
            if can_view_all:
                # View all
                pass
            elif can_view_assigned:
                if status:
                    if status == "pending":
                        # Pending: assigned to me OR unassigned OR submitted by me
                        query = query.filter(Q(assignee_id=user_id) | Q(assignee_id__isnull=True) | Q(submitter_id=user_id))
                    else:
                        query = query.filter(Q(assignee_id=user_id) | Q(submitter_id=user_id))
                else:
                    # All: assigned to me OR (pending AND unassigned) OR submitted by me
                    query = query.filter(
                        Q(assignee_id=user_id) | 
                        Q(status='pending', assignee_id__isnull=True) |
                        Q(submitter_id=user_id)
                    )
            else:
                # Users only see their own
                query = query.filter(submitter_id=user_id)
            
        total = await query.count()
        orders = await query.order_by("-created_at").offset(offset).limit(page_size).all()
        
        # Fetch related info manually
        # Users (submitter, assignee) and Device
        s_ids = {o.submitter_id for o in orders if o.submitter_id}
        a_ids = {o.assignee_id for o in orders if o.assignee_id}
        d_ids = {o.device_id for o in orders if o.device_id}
        l_ids = {o.location_id for o in orders if o.location_id}
        
        all_u_ids = s_ids | a_ids
        users = await User.filter(id__in=list(all_u_ids)).all()
        user_map = {u.id: u.username for u in users}
        
        devices = await NetworkDevice.filter(id__in=list(d_ids)).all()
        device_map = {d.id: d.device_name for d in devices}

        locations = await LocationNode.filter(id__in=list(l_ids)).all()
        location_map = {l.id: l.name for l in locations}
        
        items = []
        for o in orders:
            submitter_name = user_map.get(o.submitter_id) if o.submitter_id else None
            if o.submitter_id and not submitter_name:
                submitter_name = DELETED_USER_DISPLAY_NAME
            assignee_name = user_map.get(o.assignee_id) if o.assignee_id else None
            if o.assignee_id and not assignee_name:
                assignee_name = DELETED_USER_DISPLAY_NAME
            items.append({
                "id": o.id,
                "title": o.title,
                "description": o.description,
                "submitter_id": o.submitter_id,
                "submitter_name": submitter_name,
                "device_id": o.device_id,
                "device_name": device_map.get(o.device_id),
                "location_id": o.location_id,
                "location_name": location_map.get(o.location_id),
                "assignee_id": o.assignee_id,
                "assignee_name": assignee_name,
                "priority": o.priority,
                "status": o.status,
                "actual_completion_time": o.actual_completion_time,
                "created_at": o.created_at,
                "updated_at": o.updated_at
            })
            
        return {
            "total": total,
            "items": items
        }

    @staticmethod
    async def get_order_detail(order_id: int) -> Optional[dict]:
        """
        获取工单详情
        包含基本信息、操作日志、评论、工作日志等
        """
        o = await RepairOrder.filter(id=order_id).first()
        if not o:
            return None
            
        # Fetch related info
        submitter = await User.filter(id=o.submitter_id).first()
        assignee = await User.filter(id=o.assignee_id).first() if o.assignee_id else None
        device = await NetworkDevice.filter(id=o.device_id).first() if o.device_id else None
        location = await LocationNode.filter(id=o.location_id).first() if o.location_id else None
        
        submitter_name = submitter.username if submitter else None
        if o.submitter_id and not submitter_name:
            submitter_name = DELETED_USER_DISPLAY_NAME
        assignee_name = assignee.username if assignee else None
        if o.assignee_id and not assignee_name:
            assignee_name = DELETED_USER_DISPLAY_NAME
        order = {
            "id": o.id,
            "title": o.title,
            "description": o.description,
            "submitter_id": o.submitter_id,
            "submitter_name": submitter_name,
            "device_id": o.device_id,
            "device_name": device.device_name if device else None,
            "location_id": o.location_id,
            "location_name": location.name if location else None,
            "assignee_id": o.assignee_id,
            "assignee_name": assignee_name,
            "priority": o.priority,
            "status": o.status,
            "actual_completion_time": o.actual_completion_time,
            "created_at": o.created_at,
            "updated_at": o.updated_at
        }
        
        # Fetch logs
        logs = await OrderLog.filter(order_id=order_id).order_by("created_at").all()
        # Fetch operator names
        op_ids = {l.operator_id for l in logs}
        operators = await User.filter(id__in=list(op_ids)).all()
        op_map = {u.id: u.username for u in operators}
        
        order['logs'] = []
        for l in logs:
            operator_name = op_map.get(l.operator_id)
            if l.operator_id and not operator_name:
                operator_name = DELETED_USER_DISPLAY_NAME
            order['logs'].append({
                "id": l.id,
                "order_id": l.order_id,
                "operator_id": l.operator_id,
                "operator_name": operator_name,
                "action": l.action,
                "from_status": l.from_status,
                "to_status": l.to_status,
                "remark": l.remark,
                "created_at": l.created_at
            })
        
        # Fetch review
        review = await OrderReview.filter(order_id=order_id).first()
        if review:
            order['review'] = {
                "id": review.id,
                "order_id": review.order_id,
                "rating": review.rating,
                "comment": review.comment,
                "response_time_rating": review.response_time_rating,
                "service_quality_rating": review.service_quality_rating,
                "created_at": review.created_at
            }
        
        # Fetch work logs
        order['work_logs'] = await RepairOrderService.get_work_logs(order_id)

        imgs = await RepairImage.filter(order_id=order_id, work_log_id__isnull=True).order_by("created_at").all()
        order["images"] = []
        for img in imgs or []:
            url = str(img.url or "").strip()
            if url:
                order["images"].append(ImageStorageService.normalize_public_url(url))
            else:
                order["images"].append(f"/api/v1/repair-images/{int(img.id)}/content")
            
        return order

    @staticmethod
    async def update_order(
        order_id: int, 
        data: RepairOrderUpdate, 
        operator_id: int, 
        skip_log: bool = False,
        assign_reason: str = None
    ) -> bool:
        """
        更新工单信息 (状态、指派人、优先级等)
        """
        # Check current status
        # We need the current status for logging
        current = await RepairOrder.filter(id=order_id).first()
        if not current:
            return False
            
        updates = {}
        new_assignee_id = None
        
        if data.status:
            if not skip_log and current.status != data.status:
                # Log status change
                await RepairOrderService.log_action(order_id, operator_id, "update_status", current.status, data.status, "更新状态")
            updates['status'] = data.status

            if data.status == "completed":
                import datetime
                updates['actual_completion_time'] = datetime.datetime.now()
            
        if data.assignee_id is not None:
            try:
                aid = int(data.assignee_id)
            except Exception:
                aid = None
            if aid is not None and aid > 0:
                if not skip_log:
                    await RepairOrderService.log_action(order_id, operator_id, "assign", current.status, current.status, f"指派给用户ID: {aid}")
                updates['assignee_id'] = aid
                if current.assignee_id != aid:
                    new_assignee_id = aid

        if data.title is not None:
            t = str(data.title or "").strip()
            if t:
                updates["title"] = t

        if data.priority is not None:
            p = str(data.priority or "").strip()
            if p:
                updates['priority'] = p

        if data.description is not None:
            d = str(data.description or "").strip()
            if d:
                updates['description'] = d

        if data.device_id is not None:
            try:
                did = int(data.device_id)
            except Exception:
                did = None
            if did is not None and did > 0:
                updates["device_id"] = did

        if data.location_id is not None:
            try:
                lid = int(data.location_id)
            except Exception:
                lid = None
            if lid is not None and lid > 0:
                updates["location_id"] = lid
            
        if not updates:
            return True
            
        await RepairOrder.filter(id=order_id).update(**updates)

        # 发送派单通知
        if new_assignee_id:
            from app.services.notification_service import NotificationService
            import logging
            try:
                # Use updated data if present, else current
                # Note: RepairOrderUpdate fields are optional
                t = str(updates.get("title") or current.title)
                p = str(updates.get("priority") or current.priority)
                
                await NotificationService.notify_repair_order_assigned(
                    order_id=order_id,
                    title=str(t),
                    assignee_id=new_assignee_id,
                    priority=str(p),
                    reason=assign_reason or "工单指派"
                )
            except Exception as e:
                logging.getLogger(__name__).error(f"发送派单通知失败: {e}")

        return True

    @staticmethod
    async def delete_order(order_id: int) -> bool:
        oid = int(order_id)
        current = await RepairOrder.filter(id=oid).first()
        if not current:
            return False

        work_log_ids = await WorkLog.filter(order_id=oid).values_list("id", flat=True)
        work_log_ids = [int(x) for x in (work_log_ids or []) if x is not None]

        img_query = Q(order_id=oid)
        if work_log_ids:
            img_query = img_query | Q(work_log_id__in=work_log_ids)

        images = await RepairImage.filter(img_query).all()
        for img in images or []:
            provider = str(getattr(img, "storage_provider", "") or "").strip()
            key = str(getattr(img, "object_key", "") or "").strip()
            if provider == "remote_api":
                if not key:
                    raise RemoteImageApiError("删除工单失败: 图片 key 为空")
                await ImageStorageService.delete_remote(key)

        await RepairImage.filter(img_query).delete()
        await WorkLog.filter(order_id=oid).delete()
        await OrderReview.filter(order_id=oid).delete()
        await OrderLog.filter(order_id=oid).delete()
        await RepairOrder.filter(id=oid).delete()
        return True

    @staticmethod
    async def log_action(order_id: int, operator_id: int, action: str, from_status: str, to_status: str, remark: str = ""):
        """
        记录工单操作日志
        """
        await OrderLog.create(
            order_id=order_id,
            operator_id=operator_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            remark=remark
        )

    @staticmethod
    async def submit_review(order_id: int, data: OrderReviewCreate):
        await OrderReview.create(
            order_id=order_id,
            rating=data.rating,
            comment=data.comment,
            response_time_rating=data.response_time_rating,
            service_quality_rating=data.service_quality_rating
        )

    @staticmethod
    async def add_work_log(order_id: int, operator_id: int, content: str, images: Optional[list] = None) -> WorkLog:
        normalized = []
        for item in (images or []):
            if item is None:
                continue
            if isinstance(item, int):
                normalized.append(int(item))
                continue
            if isinstance(item, str):
                s = item.strip()
                if not s:
                    continue
                if s.isdigit():
                    normalized.append(int(s))
                    continue
                normalized.append(s)
                continue
            try:
                normalized.append(int(item))
            except Exception:
                continue

        log = await WorkLog.create(
            order_id=order_id,
            operator_id=operator_id,
            content=content,
            images=normalized
        )
        image_ids = [x for x in normalized if isinstance(x, int)]
        if image_ids:
            await RepairImage.filter(id__in=image_ids).update(order_id=order_id, work_log_id=log.id)
        return log

    @staticmethod
    async def get_work_logs(order_id: int) -> List[dict]:
        """
        获取工单工作日志列表
        """
        logs = await WorkLog.filter(order_id=order_id).order_by("created_at").all()
        if not logs:
            return []
            
        op_ids = {l.operator_id for l in logs}
        operators = await User.filter(id__in=list(op_ids)).all()
        op_map = {u.id: u.username for u in operators}

        image_ids = []
        for l in logs:
            for it in (l.images or []):
                if isinstance(it, int):
                    image_ids.append(int(it))
                elif isinstance(it, str) and it.strip().isdigit():
                    image_ids.append(int(it.strip()))
        image_ids = list({i for i in image_ids if i > 0})
        images_map = {}
        if image_ids:
            imgs = await RepairImage.filter(id__in=image_ids).all()
            for img in imgs:
                url = str(img.url or "").strip()
                if url:
                    images_map[int(img.id)] = ImageStorageService.normalize_public_url(url)
                else:
                    images_map[int(img.id)] = f"/api/v1/repair-images/{int(img.id)}/content"

        out = []
        for l in logs:
            resolved = []
            for it in (l.images or []):
                if it is None:
                    continue
                if isinstance(it, int):
                    u = images_map.get(int(it))
                    if u:
                        resolved.append(u)
                    continue
                if isinstance(it, str):
                    s = it.strip()
                    if not s:
                        continue
                    if s.isdigit():
                        u = images_map.get(int(s))
                        if u:
                            resolved.append(u)
                        continue
                    if s.startswith("/uploads/") or "://" in s:
                        resolved.append(ImageStorageService.normalize_public_url(s))
                    else:
                        resolved.append(s)
                    continue
            out.append({
                "id": l.id,
                "order_id": l.order_id,
                "operator_id": l.operator_id,
                "operator_name": op_map.get(l.operator_id),
                "content": l.content,
                "images": resolved,
                "created_at": l.created_at
            })
        return out
