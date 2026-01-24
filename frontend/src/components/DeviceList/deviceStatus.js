export function normalizeFsmState(device) {
  const v =
    (device && (device.fsmState || device.fsm_state || device.rawStatus || device.raw_status)) ||
    ''
  return String(v || '').trim().toLowerCase()
}

export function normalizeConnectivity(device) {
  const v = device && (device.connectivity || device.status)
  const s = String(v || '').trim().toLowerCase()
  if (s === 'online' || s === 'offline') return s
  if (device && typeof device.online_status === 'boolean') return device.online_status ? 'online' : 'offline'
  if (device && typeof device.onlineStatus === 'boolean') return device.onlineStatus ? 'online' : 'offline'
  const label = normalizeDisplayStatus(device)
  if (label === '在线' || label === '采集中' || label === '检测中' || label === '恢复中' || label === '异常' || label === '重载中') return 'online'
  return 'offline'
}

export function normalizeDisplayStatus(device) {
  const v =
    (device && (device.displayStatus || device.display_status || device.status || '')) ||
    ''
  const s = String(v || '').trim()
  const low = s.toLowerCase()
  if (low === 'online' || low === 'offline') return ''
  return s
}

export function getDeviceStatusText(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const display = normalizeDisplayStatus(device)
  const reason = String((device && (device.fsmReason || device.fsm_reason || '')) || '')

  if (connectivity !== 'offline') {
    if (display) return display
    if (fsm === 'online') return '在线'
    if (fsm === 'recovering') return '恢复中'
    if (fsm === 'degraded') return '异常'
    if (fsm === 'checking') return '检测中'
    if (fsm === 'collecting') return '采集中'
    if (fsm === 'reloading') return '重载中'
    if (fsm === 'init') return '初始化中'
    return '在线'
  }

  if (reason.includes('timeout')) return '连接超时'
  if (reason.includes('auth')) return '认证失败'
  if (reason.includes('unreachable')) return '不可达'
  if (display && display !== '在线') return display
  return '离线'
}

export function getDeviceStatusTagType(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const text = getDeviceStatusText(device)

  if (connectivity === 'offline') return 'danger'
  if (fsm === 'online') return 'success'
  if (fsm === 'recovering' || fsm === 'checking' || fsm === 'collecting' || fsm === 'reloading') return 'warning'
  if (fsm === 'degraded') return 'danger'
  if (fsm === 'init' || text === '待加载' || text === '初始化中') return 'info'
  return 'info'
}

export function isSshEnabled(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const display = normalizeDisplayStatus(device)

  if (connectivity !== 'online') return false
  if (fsm === 'offline' || fsm === 'init') return false
  if (display === '待加载' || display === '初始化中' || display === '未知') return false
  return true
}
