import assert from 'node:assert/strict'
import {
  getDataHealthText,
  getLastUpdatedText,
  getDeviceStatusText,
} from '../src/components/DeviceList/deviceStatus.js'

const now = Date.now()

const onlineFresh = {
  connectivity: 'online',
  fsm_state: 'online',
  stale: false,
  age_seconds: 5,
  last_updated: String(Math.floor(now / 1000) - 5),
}

const onlineStale = {
  connectivity: 'online',
  fsm_state: 'online',
  stale: true,
  age_seconds: 400,
  last_updated: String(Math.floor(now / 1000) - 400),
}

const degraded = {
  connectivity: 'online',
  fsm_state: 'degraded',
  stale: false,
  age_seconds: 12,
  last_updated: String(Math.floor(now / 1000) - 12),
}

const offline = {
  connectivity: 'offline',
  fsm_state: 'offline',
  stale: false,
  age_seconds: 0,
  last_updated: '',
}

assert.equal(getDataHealthText(onlineFresh, now), '正常')
assert.equal(getDataHealthText(onlineStale, now), '已过期')
assert.equal(getDataHealthText(degraded, now), '部分异常')
assert.equal(getDataHealthText(offline, now), '不可用')

assert.equal(getDeviceStatusText(onlineFresh, now), '在线')
assert.equal(getDeviceStatusText(onlineStale, now), '在线')
assert.equal(getDeviceStatusText(degraded, now), '异常')
assert.equal(getDeviceStatusText(offline, now), '离线')

assert.notEqual(getLastUpdatedText(onlineFresh), '--')
assert.equal(getLastUpdatedText(offline), '--')

console.log('deviceStatusPresentation tests passed')
