<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { post, request, setSessionToken } from './api'
import type { Alert, AppManifest, Backup, Container, Project, Service, SystemSnapshot } from './types'

const active = ref('overview')
const authenticated = ref(Boolean(window.sessionStorage.getItem('lightops-token')))
const loginForm = ref({ username: 'admin', password: '', totp: '' })
const loginLoading = ref(false)
const loading = ref(false)
const error = ref('')
const system = ref<SystemSnapshot | null>(null)
const services = ref<Service[]>([])
const apps = ref<AppManifest[]>([])
const containers = ref<Container[]>([])
const projects = ref<Project[]>([])
const alerts = ref<Alert[]>([])
const backups = ref<Backup[]>([])
const backupForm = ref({ name: '', sources: '' })
let timer: number | undefined

const titles: Record<string, string> = {
  overview: '系統總覽', services: '服務管理', docker: 'Docker 容器', apps: '軟體中心', projects: '專案部署', backups: '備份管理',
}

const disk = computed(() => system.value?.disks[0])
const uptime = computed(() => {
  const seconds = system.value?.uptime_seconds ?? 0
  return `${Math.floor(seconds / 86400)} 天 ${Math.floor((seconds % 86400) / 3600)} 小時`
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [snapshot, serviceList, appList, containerList, projectList, alertList, backupList] = await Promise.all([
      request<SystemSnapshot>('system'),
      request<Service[]>('services'),
      request<AppManifest[]>('apps'),
      request<Container[]>('docker/containers'),
      request<Project[]>('projects'),
      request<Alert[]>('alerts'),
      request<Backup[]>('backups'),
    ])
    system.value = snapshot
    services.value = serviceList
    apps.value = appList
    containers.value = containerList
    projects.value = projectList
    alerts.value = alertList
    backups.value = backupList
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法取得伺服器狀態'
  } finally {
    loading.value = false
  }
}

async function login() {
  loginLoading.value = true
  try {
    const session = await post<{ token: string }>('auth/login', loginForm.value)
    setSessionToken(session.token)
    authenticated.value = true
    loginForm.value.password = ''
    loginForm.value.totp = ''
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '登入失敗')
  } finally {
    loginLoading.value = false
  }
}

async function action(path: string, description: string, dangerous = false) {
  if (dangerous) await ElMessageBox.confirm(`確定要${description}？`, '高風險操作確認', { type: 'warning' })
  try {
    await post(path)
    ElMessage.success(`${description}完成`)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : `${description}失敗`)
  }
}

async function createBackup() {
  const sources = backupForm.value.sources.split(',').map(item => item.trim()).filter(Boolean)
  if (!backupForm.value.name || !sources.length) return ElMessage.warning('請填寫備份名稱與來源路徑')
  await ElMessageBox.confirm(`確定要備份 ${sources.join('、')}？`, '建立備份', { type: 'warning' })
  try {
    await post('backups', { name: backupForm.value.name, sources })
    backupForm.value = { name: '', sources: '' }
    ElMessage.success('備份完成')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '備份失敗')
  }
}

const bytes = (value: number) => `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
const appAction = (item: AppManifest) => item.installed ? (item.service?.name ? 'restart' : 'update') : 'install'
const appActionLabel = (item: AppManifest) => item.installed ? (item.service?.name ? '重新啟動' : '更新') : '安裝'

onMounted(async () => {
  if (authenticated.value) await load()
  timer = window.setInterval(() => authenticated.value && load(), 30_000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <main v-if="!authenticated" class="login-page">
    <section class="login-card">
      <div class="brand login-brand"><span class="brand-mark">L</span><div><strong>LightOps</strong><small>Server Console</small></div></div>
      <p class="eyebrow">SECURE ACCESS</p>
      <h1>登入管理平台</h1>
      <p>請使用伺服器管理員帳號登入。</p>
      <el-form label-position="top" @submit.prevent="login">
        <el-form-item label="帳號"><el-input v-model="loginForm.username" autocomplete="username" /></el-form-item>
        <el-form-item label="密碼"><el-input v-model="loginForm.password" type="password" autocomplete="current-password" show-password /></el-form-item>
        <el-form-item label="兩步驗證碼（如已啟用）"><el-input v-model="loginForm.totp" inputmode="numeric" maxlength="6" autocomplete="one-time-code" /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="loginLoading">登入</el-button>
      </el-form>
      <small>首次使用請先執行 sudo lightops reset-password</small>
    </section>
  </main>
  <div v-else class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">L</span><div><strong>LightOps</strong><small>Server Console</small></div></div>
      <nav>
        <button v-for="item in [['overview','總覽'],['services','服務'],['docker','Docker'],['apps','軟體中心'],['projects','專案'],['backups','備份']]" :key="item[0]" :class="{ active: active === item[0] }" @click="active = item[0]">{{ item[1] }}</button>
      </nav>
      <div class="server-state"><span></span><div><strong>本機伺服器</strong><small>LightOps 0.1.0</small></div></div>
    </aside>

    <main v-loading="loading">
      <header><div><p class="eyebrow">OPERATIONS CENTER</p><h1>{{ titles[active] }}</h1></div><el-button @click="load">重新整理</el-button></header>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-alert v-for="alert in alerts" :key="`${alert.resource}-${alert.severity}`" :title="alert.message" :type="alert.severity === 'warning' ? 'warning' : 'error'" show-icon />

      <template v-if="active === 'overview' && system">
        <section class="metrics">
          <article><small>CPU 使用率</small><strong>{{ system.cpu_percent.toFixed(1) }}%</strong><el-progress :percentage="system.cpu_percent" :show-text="false" /></article>
          <article><small>記憶體</small><strong>{{ system.memory.percent.toFixed(1) }}%</strong><p>{{ bytes(system.memory.used) }} / {{ bytes(system.memory.total) }}</p></article>
          <article><small>主要磁碟</small><strong>{{ disk?.percent.toFixed(1) ?? 0 }}%</strong><p>{{ disk?.path ?? '—' }}</p></article>
          <article><small>運行時間</small><strong class="compact">{{ uptime }}</strong><p>{{ system.kernel_version }}</p></article>
        </section>
        <section class="grid-two">
          <article class="panel"><div class="panel-title"><h2>服務健康</h2><span>{{ services.filter(item => item.active).length }}/{{ services.length }} 運行中</span></div><div class="service-row" v-for="service in services" :key="service.name"><span :class="['dot', { online: service.active }]" /><strong>{{ service.name }}</strong><small>{{ service.status }}</small></div></article>
          <article class="panel"><div class="panel-title"><h2>主機資訊</h2></div><dl><dt>作業系統</dt><dd>{{ system.operating_system }}</dd><dt>系統負載</dt><dd>{{ system.load_average.map(value => value.toFixed(2)).join(' / ') }}</dd><dt>網路接收</dt><dd>{{ bytes(system.network.bytes_received) }}</dd><dt>網路傳送</dt><dd>{{ bytes(system.network.bytes_sent) }}</dd></dl></article>
        </section>
      </template>

      <section v-else-if="active === 'services'" class="panel table-panel">
        <el-table :data="services"><el-table-column prop="name" label="服務" /><el-table-column prop="status" label="狀態" /><el-table-column label="操作"><template #default="scope"><el-button size="small" @click="action(`services/${scope.row.name}/restart`, `重新啟動 ${scope.row.name}`, true)">重新啟動</el-button></template></el-table-column></el-table>
      </section>
      <section v-else-if="active === 'docker'" class="panel table-panel">
        <el-table :data="containers"><el-table-column prop="name" label="容器" /><el-table-column prop="image" label="映像" /><el-table-column prop="status" label="狀態" /><el-table-column label="操作"><template #default="scope"><el-button size="small" @click="action(`docker/containers/${scope.row.id}/restart`, `重新啟動 ${scope.row.name}`, true)">重新啟動</el-button></template></el-table-column></el-table>
      </section>
      <section v-else-if="active === 'apps'" class="cards">
        <article v-for="item in apps" :key="item.name" class="app-card"><div><small>{{ item.category }}</small><h3>{{ item.display_name }}</h3><p>{{ item.description }}</p></div><div class="app-footer"><el-tag :type="item.installed ? 'success' : 'info'">{{ item.installed ? item.status : '未安裝' }}</el-tag><el-button size="small" @click="action(`apps/${item.name}/${appAction(item)}`, `${appActionLabel(item)} ${item.display_name}`, true)">{{ appActionLabel(item) }}</el-button></div></article>
      </section>
      <section v-else-if="active === 'projects'" class="panel table-panel">
        <el-table :data="projects"><el-table-column prop="name" label="專案" /><el-table-column prop="project_type" label="類型" /><el-table-column prop="branch" label="分支" /><el-table-column prop="deploy_path" label="部署路徑" /><el-table-column label="操作"><template #default="scope"><el-button size="small" type="primary" @click="action(`projects/${scope.row.code}/deploy`, `部署 ${scope.row.name}`, true)">部署</el-button><el-button size="small" @click="action(`projects/${scope.row.code}/rollback`, `回滾 ${scope.row.name}`, true)">回滾</el-button></template></el-table-column></el-table>
      </section>
      <section v-else class="panel table-panel">
        <div class="backup-create"><el-input v-model="backupForm.name" placeholder="備份名稱（例如 website）" /><el-input v-model="backupForm.sources" placeholder="來源絕對路徑，多個以逗號分隔" /><el-button type="primary" @click="createBackup">建立備份</el-button></div>
        <el-table :data="backups"><el-table-column prop="name" label="名稱" /><el-table-column prop="filename" label="檔案" /><el-table-column label="大小"><template #default="scope">{{ (scope.row.size / 1024 / 1024).toFixed(2) }} MB</template></el-table-column><el-table-column prop="created_at" label="建立時間" /></el-table>
      </section>
    </main>
  </div>
</template>
