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

function formatOfflineReason(reason) {
  const raw = String(reason || '').trim()
  if (!raw) return ''

  const low = raw.toLowerCase()

  if (low.includes('timed out') || low.includes('timeout') || low.includes('read timeout') || low.includes('netmikotimeoutexception')) {
    return '连接超时'
  }

  if (
    low.includes('netmikoauthenticationexception') ||
    low.includes('authentication failed') ||
    low.includes('bad authentication type') ||
    low.includes('not allowed')
  ) {
    return '认证失败'
  }

  if (
    low.includes('connection refused') ||
    low.includes('no route to host') ||
    low.includes('name or service not known') ||
    low.includes('nodename nor servname') ||
    low.includes('unreachable')
  ) {
    return '不可达'
  }

  if (
    low.includes('connection reset by peer') ||
    low.includes('broken pipe') ||
    low.includes('socket is closed') ||
    low.includes('eoferror') ||
    low.includes('bad file descriptor')
  ) {
    return '连接中断'
  }

  const stripped = raw.replace(/^[A-Za-z_][A-Za-z0-9_]*?(Exception|Error):\s*/u, '').trim()
  return stripped || raw
}

export function getDeviceStatusText(device, nowEpochMs) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const display = normalizeDisplayStatus(device)
  const reason = String((device && (device.fsmReason || device.fsm_reason || '')) || '')
  const stale = !!(device && device.stale)

  void nowEpochMs

  if (connectivity !== 'offline') {
    if (display) return stale ? `${display}（过期）` : display
    if (fsm === 'online') return '在线'
    if (fsm === 'recovering') return '恢复中'
    if (fsm === 'degraded') return '异常'
    if (fsm === 'checking') return '检测中'
    if (fsm === 'collecting') return '采集中'
    if (fsm === 'reloading') return '重载中'
    if (fsm === 'init') return '初始化中'
    return '在线'
  }

  void reason
  if (display && display !== '在线' && display !== '离线') return stale ? `${display}（过期）` : display
  return stale ? '离线（过期）' : '离线'
}

export function getDeviceStatusTagType(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const text = getDeviceStatusText(device)
  const stale = !!(device && device.stale)

  if (text === '无运行态' || text === '未知') return 'info'
  if (stale) return 'warning'
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
  const stale = !!(device && device.stale)

  if (connectivity !== 'online') return false
  if (stale) return false
  if (fsm === 'offline' || fsm === 'init') return false
  if (fsm === 'checking' || fsm === 'collecting' || fsm === 'reloading') return false
  if (display === '待加载' || display === '初始化中' || display === '未知' || display === '无运行态') return false
  return true
}
