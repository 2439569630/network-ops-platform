<template>
  <div class="smp-container">
    <div class="smp-header">
      <el-button @click="goBack">返回</el-button>
      <div class="smp-title">发布站内消息</div>
      <div class="smp-spacer"></div>
    </div>

    <el-card shadow="never" class="smp-card">
      <el-form label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="120" show-word-limit />
        </el-form-item>

        <el-form-item label="范围">
          <el-space wrap alignment="center">
            <el-switch
              v-model="form.is_global"
              inline-prompt
              active-text="全站"
              inactive-text="指定用户"
              :disabled="!canSendGlobal"
            />
            <el-input
              v-if="!form.is_global"
              v-model="form.target_user_id"
              placeholder="用户ID"
              style="width: 180px"
            />
          </el-space>
        </el-form-item>

        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="10" maxlength="2000" show-word-limit />
        </el-form-item>

        <el-form-item>
          <el-space>
            <el-button @click="goBack">取消</el-button>
            <el-button type="primary" :loading="submitting" @click="submit">发布</el-button>
          </el-space>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'
import { messageCenterDataStore } from '@/components/MessageCenter/date'

const router = useRouter()
const store = homeDataStore()
const msgStore = messageCenterDataStore()

const submitting = ref(false)
const form = reactive({
  title: '',
  content: '',
  is_global: true,
  target_user_id: '',
})

const isSuper = computed(() => Boolean(store.isSuper))
const perms = computed(() => (Array.isArray(store.permissions) ? store.permissions.map(String) : []))
const canSend = computed(() => isSuper.value || perms.value.includes('sys:message:publish'))
const canSendGlobal = computed(() => isSuper.value || perms.value.includes('sys:notify:global'))

const goBack = () => {
  router.push({ name: 'message', query: { tab: 'site' } })
}

const submit = async () => {
  if (!canSend.value) return
  if (submitting.value) return

  const title = String(form.title || '').trim()
  const content = String(form.content || '').trim()
  if (!title) {
    ElMessage.warning('标题不能为空')
    return
  }
  if (!content) {
    ElMessage.warning('内容不能为空')
    return
  }

  submitting.value = true
  try {
    const payload = {
      title,
      content,
      is_global: Boolean(form.is_global),
      target_user_id: form.is_global ? null : (form.target_user_id ? Number(form.target_user_id) : null),
    }
    const res = await axios.post('/api/v1/notifications/site-messages', payload)
    if (res?.data?.code === 200) {
      ElMessage.success(res?.data?.message || '发布成功')
      if (res?.data?.data) {
        msgStore.upsertSiteMessage(res.data.data)
        await msgStore.fetchSiteMessageUnreadCount()
      }
      goBack()
      return
    }
    ElMessage.error(res?.data?.message || '发布失败')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '发布失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  store.syncAuthFromToken()
  await store.fetchPermissions()
  form.is_global = Boolean(canSendGlobal.value)
  if (!canSend.value) {
    ElMessage.error('权限不足')
    goBack()
    return
  }
})
</script>

<style scoped>
.smp-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.smp-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.smp-title {
  font-size: 18px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.smp-spacer {
  flex: 1;
}

.smp-card {
  flex: 1;
  overflow: auto;
}
</style>
