-- 删除 network_devices 表中废弃的 location 字段
ALTER TABLE network_devices DROP COLUMN IF EXISTS location;

-- 删除 users 表中废弃的 permissions 字段
ALTER TABLE users DROP COLUMN IF EXISTS permissions;

-- 删除 location_nodes 表中废弃的 manager_dept 字段
ALTER TABLE location_nodes DROP COLUMN IF EXISTS manager_dept;

-- 删除 location_nodes 表中废弃的基础信息字段
ALTER TABLE location_nodes DROP COLUMN IF EXISTS manager;
ALTER TABLE location_nodes DROP COLUMN IF EXISTS phone;
ALTER TABLE location_nodes DROP COLUMN IF EXISTS capacity;
ALTER TABLE location_nodes DROP COLUMN IF EXISTS area;
