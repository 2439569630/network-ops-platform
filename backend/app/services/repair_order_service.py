import json
from datetime import datetime
from typing import List, Optional, Dict
from app.core.database import db
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, OrderReviewCreate

class RepairOrderService:
    @staticmethod
    async def create_order(data: RepairOrderCreate, submitter_id: int) -> int:
        sql = """
            INSERT INTO repair_orders (
                title, description, submitter_id, device_id, priority, status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, 'pending', NOW(), NOW())
            RETURNING id
        """
        order_id = await db.fetch_val(
            sql, 
            data.title, 
            data.description, 
            submitter_id, 
            data.device_id, 
            data.priority
        )
        
        # Log creation
        await RepairOrderService.log_action(order_id, submitter_id, "create", "", "pending", "创建工单")
        return order_id

    @staticmethod
    async def get_order_list(
        page: int = 1, 
        page_size: int = 10, 
        status: Optional[str] = None, 
        user_id: Optional[int] = None,
        role_level: int = 2  # 0:admin, 1:maintenance, 2:user
    ) -> Dict:
        offset = (page - 1) * page_size
        
        # Base query
        where_clauses = []
        params = []
        idx = 1
        
        if status:
            where_clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1
            
        # Role based filtering
        if role_level == 2:
            # Users only see their own
            where_clauses.append(f"submitter_id = ${idx}")
            params.append(user_id)
            idx += 1
        elif role_level == 1:
            # Maintenance see assigned or unassigned(pending) or all? 
            # Design: 查看所有工单 - ✓(部分)
            # Usually see orders assigned to them OR pending orders (pool)
            pass # Currently allow viewing all, or filter by assignee if needed
            
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Count
        count_sql = f"SELECT COUNT(*) FROM repair_orders {where_sql}"
        total = await db.fetch_val(count_sql, *params)
        
        # Data
        data_sql = f"""
            SELECT r.*, u.username as submitter_name, d.device_name, a.username as assignee_name
            FROM repair_orders r
            LEFT JOIN users u ON r.submitter_id = u.id
            LEFT JOIN network_devices d ON r.device_id = d.id
            LEFT JOIN users a ON r.assignee_id = a.id
            {where_sql}
            ORDER BY r.created_at DESC
            LIMIT ${idx} OFFSET ${idx+1}
        """
        params.append(page_size)
        params.append(offset)
        
        rows = await db.fetch_all(data_sql, *params)
        return {
            "total": total,
            "items": [dict(r) for r in rows]
        }

    @staticmethod
    async def get_order_detail(order_id: int) -> Optional[dict]:
        sql = """
            SELECT r.*, u.username as submitter_name, d.device_name, a.username as assignee_name
            FROM repair_orders r
            LEFT JOIN users u ON r.submitter_id = u.id
            LEFT JOIN network_devices d ON r.device_id = d.id
            LEFT JOIN users a ON r.assignee_id = a.id
            WHERE r.id = $1
        """
        row = await db.fetch_one(sql, order_id)
        if not row:
            return None
            
        order = dict(row)
        
        # Fetch logs
        log_sql = """
            SELECT l.*, u.username as operator_name 
            FROM order_logs l
            LEFT JOIN users u ON l.operator_id = u.id
            WHERE l.order_id = $1 ORDER BY l.created_at ASC
        """
        logs = await db.fetch_all(log_sql, order_id)
        order['logs'] = [dict(l) for l in logs]
        
        # Fetch review
        review_sql = "SELECT * FROM order_reviews WHERE order_id = $1"
        review = await db.fetch_one(review_sql, order_id)
        if review:
            order['review'] = dict(review)
            
        return order

    @staticmethod
    async def update_order(order_id: int, data: RepairOrderUpdate, operator_id: int) -> bool:
        # Check current status
        current = await RepairOrderService.get_order_detail(order_id)
        if not current:
            return False
            
        updates = []
        params = []
        idx = 1
        
        if data.status:
            updates.append(f"status = ${idx}")
            params.append(data.status)
            idx += 1
            # Log status change
            await RepairOrderService.log_action(order_id, operator_id, "update_status", current['status'], data.status, "更新状态")
            
        if data.assignee_id:
            updates.append(f"assignee_id = ${idx}")
            params.append(data.assignee_id)
            idx += 1
            await RepairOrderService.log_action(order_id, operator_id, "assign", current['status'], current['status'], f"指派给用户ID: {data.assignee_id}")

        if data.priority:
            updates.append(f"priority = ${idx}")
            params.append(data.priority)
            idx += 1
            
        if data.description:
            updates.append(f"description = ${idx}")
            params.append(data.description)
            idx += 1
            
        if not updates:
            return True
            
        updates.append(f"updated_at = NOW()")
        
        sql = f"UPDATE repair_orders SET {', '.join(updates)} WHERE id = ${idx}"
        params.append(order_id)
        
        await db.execute(sql, *params)
        return True

    @staticmethod
    async def log_action(order_id: int, operator_id: int, action: str, from_status: str, to_status: str, remark: str = ""):
        sql = """
            INSERT INTO order_logs (order_id, operator_id, action, from_status, to_status, remark, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """
        await db.execute(sql, order_id, operator_id, action, from_status, to_status, remark)

    @staticmethod
    async def submit_review(order_id: int, data: OrderReviewCreate):
        sql = """
            INSERT INTO order_reviews (order_id, rating, comment, response_time_rating, service_quality_rating, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """
        await db.execute(sql, order_id, data.rating, data.comment, data.response_time_rating, data.service_quality_rating)
        
        # Update order status to closed? Or handled separately.
