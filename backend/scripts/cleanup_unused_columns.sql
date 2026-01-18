-- 删除 network_devices 表中废弃的 location 字段
ALTER TABLE network_devices DROP COLUMN IF EXISTS location;

-- 删除 users 表中废弃的 permissions 字段
ALTER TABLE users DROP COLUMN IF EXISTS permissions;
