<template>
  <div class="discovery-report-view">
    <header class="report-header">
      <div class="report-header-left">
        <div class="brand-block" @click="goHome">
          <div class="brand-mark">R</div>
          <div class="brand-copy">
            <small>系统详情</small>
            <strong>结果详情页</strong>
          </div>
        </div>
        <div class="report-title-block">
          <div class="eyebrow">结果详情</div>
          <h1 class="report-title">{{ heroTitle }}</h1>
          <p class="report-summary">{{ heroSummary }}</p>
        </div>
      </div>
      <div class="report-header-right">
        <button class="nav-btn ghost" @click="goHome">返回首页</button>
        <button class="nav-btn" @click="goWorkspace">返回工作台</button>
        <button class="nav-btn ghost" :disabled="loading" @click="refreshAll">{{ loading ? '刷新中…' : '刷新报告' }}</button>
      </div>
    </header>

    <main class="report-shell">
      <section class="report-main">
        <article class="report-card summary-card">
          <div class="section-head">
            <span class="section-kicker">任务摘要</span>
            <span class="section-meta mono">{{ taskData?.task_id || route.params.taskId }}</span>
          </div>
          <div class="summary-grid">
            <div class="summary-item">
              <span class="summary-label">模式</span>
              <span class="summary-value">{{ displayMode(resultData?.discovery_mode || taskData?.discovery_mode) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">状态</span>
              <span class="summary-value">{{ displayTaskStatus(taskData?.status) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">结论类型</span>
              <span class="summary-value">{{ displayResolution(resultData?.resolution_type) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">耗时</span>
              <span class="summary-value mono">{{ elapsedText }}</span>
            </div>
          </div>
          <div class="brief-block">
            <div class="brief-label">问题</div>
            <div class="brief-text">{{ taskData?.query || '--' }}</div>
          </div>
          <div class="brief-block">
            <div class="brief-label">上下文</div>
            <div class="brief-text">{{ taskData?.context || '--' }}</div>
          </div>
        </article>

        <article class="report-card">
          <div class="section-head">
            <span class="section-kicker">最终结果</span>
            <span class="section-meta mono">{{ (resultData?.candidate_rules || []).length }} 条候选规则</span>
          </div>
          <div v-if="resultData?.candidate_rules?.length" class="candidate-stack">
            <div v-for="candidate in resultData.candidate_rules" :key="candidate.candidate_id" class="candidate-card">
              <div class="candidate-head">
                <div>
                  <div class="candidate-title">{{ cleanCandidateTitle(candidate.rule_title) }}</div>
                  <div class="candidate-meta mono">{{ displayCandidateType(candidate.candidate_type) }} / {{ displayValidationStatus(candidate.validation_status) }}</div>
                </div>
                <div class="score-pair">
                  <div class="score-box">
                    <span class="score-name">依据度</span>
                    <span class="score-value mono">{{ formatScore(candidate.grounding_score) }}</span>
                  </div>
                  <div class="score-box">
                    <span class="score-name">涌现度</span>
                    <span class="score-value mono">{{ formatScore(candidate.speculation_score) }}</span>
                  </div>
                </div>
              </div>
              <p class="candidate-rule-text">{{ candidate.rule_text }}</p>
              <div class="chip-row">
                <span v-for="source in candidate.knowledge_sources || []" :key="source" class="chip">{{ displayKnowledgeSource(source) }}</span>
              </div>
              <div class="reasoning-block">
                <div class="reason-line">
                  <span class="reason-label">适用原因</span>
                  <span class="reason-text">{{ candidate.why_applicable || '暂无' }}</span>
                </div>
                <div class="reason-line">
                  <span class="reason-label">改造说明</span>
                  <span class="reason-text">{{ candidate.adaptation_note || '暂无' }}</span>
                </div>
                <div class="reason-line">
                  <span class="reason-label">验证结论</span>
                  <span class="reason-text">{{ candidate.validation_reason || '暂无' }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-panel">
            当前没有保留下来的候选规则。
          </div>
        </article>

        <article class="report-card">
          <div class="section-head">
            <span class="section-kicker">形成过程</span>
            <span class="section-meta mono">{{ orderedStageCards.length }} 个阶段</span>
          </div>
          <div class="trail-stack">
            <section v-for="card in orderedStageCards" :key="card.key" class="trail-card" :class="`trail-${card.tone}`">
              <div class="trail-head">
                <div class="trail-title-row">
                  <span class="trail-index mono">{{ card.index }}</span>
                  <span class="trail-title">{{ card.title }}</span>
                </div>
                <span class="trail-time mono">{{ card.time }}</span>
              </div>
              <p class="trail-summary">{{ card.summary }}</p>
              <div v-if="card.points?.length" class="trail-points">
                <div v-for="(point, idx) in card.points" :key="idx" class="trail-point">{{ point }}</div>
              </div>
              <details class="trail-raw">
                <summary>查看原始阶段产物</summary>
                <pre>{{ formatJson(card.raw) }}</pre>
              </details>
            </section>
          </div>
        </article>

        <article class="report-card" v-if="criticCandidate">
          <div class="section-head">
            <span class="section-kicker">校验结果</span>
            <span class="section-meta mono">{{ criticRelations.length }} 条关系</span>
          </div>
          <div class="critic-grid">
            <div class="critic-box">
              <div class="critic-title">关系映射</div>
              <div v-if="criticRelations.length" class="critic-list">
                <div v-for="(item, idx) in criticRelations" :key="idx" class="critic-item">
                  <div class="critic-item-head">
                    <span class="critic-rule">{{ item.rule_id }}</span>
                    <span class="critic-type mono">{{ displayRelationType(item.relation_type) }}</span>
                  </div>
                  <div class="critic-reason">{{ item.relation_reason }}</div>
                </div>
              </div>
              <div v-else class="empty-mini">未检测到相关规则关系。</div>
            </div>

            <div class="critic-box">
              <div class="critic-title">反例</div>
              <div v-if="criticCounterexamples.length" class="critic-list">
                <div v-for="(item, idx) in criticCounterexamples" :key="idx" class="critic-item">
                  <div class="critic-reason">{{ item }}</div>
                </div>
              </div>
              <div v-else class="empty-mini">未给出反例。</div>
            </div>

            <div class="critic-box">
              <div class="critic-title">缺口</div>
              <div v-if="criticMissing.length" class="critic-list">
                <div v-for="(item, idx) in criticMissing" :key="idx" class="critic-item">
                  <div class="critic-reason">{{ item }}</div>
                </div>
              </div>
              <div v-else class="empty-mini">未发现明显缺口。</div>
            </div>
          </div>
        </article>

        <article class="report-card" v-if="resultData?.rejected_candidates?.length || resultData?.open_questions?.length">
          <div class="section-head">
            <span class="section-kicker">待解决项</span>
            <span class="section-meta mono">{{ (resultData?.open_questions?.length || 0) + (resultData?.rejected_candidates?.length || 0) }}</span>
          </div>
          <div v-if="resultData?.open_questions?.length" class="open-block">
            <div class="block-title">待解决问题</div>
            <div v-for="(item, idx) in resultData.open_questions" :key="idx" class="open-line">{{ item }}</div>
          </div>
          <div v-if="resultData?.rejected_candidates?.length" class="open-block">
            <div class="block-title">驳回与阻塞</div>
            <div v-for="(item, idx) in resultData.rejected_candidates" :key="idx" class="reject-line">
              <div class="reject-id mono">{{ item.candidate_id || `item-${idx + 1}` }}</div>
              <div class="reject-text">{{ item.reason }}</div>
            </div>
          </div>
        </article>
      </section>

      <aside class="report-side">
        <section class="report-card side-card">
          <div class="section-head">
            <span class="section-kicker">阶段记录</span>
            <span class="section-meta mono">{{ stageMetrics.length }}</span>
          </div>
          <div class="ledger-stack">
            <div v-for="item in stageMetrics" :key="item.stage" class="ledger-row">
              <div class="ledger-row-head">
                <span class="ledger-stage">{{ stageTitle(item.stage) }}</span>
                <span class="ledger-duration mono">{{ item.duration_seconds ?? '--' }}s</span>
              </div>
              <div class="ledger-time mono">{{ item.start_at }}</div>
            </div>
          </div>
        </section>

        <section class="report-card side-card">
          <div class="section-head">
            <span class="section-kicker">结果来源</span>
            <span class="section-meta mono">{{ displayMode(provenanceSummary.mode) }}</span>
          </div>
          <div class="provenance-summary">
            <div class="summary-line">
              <span class="label">模式</span>
              <span class="value mono">{{ displayMode(provenanceSummary.mode) }}</span>
            </div>
            <div class="summary-line">
              <span class="label">通用知识</span>
              <span class="value mono">{{ (provenanceSummary.general_knowledge_used ?? false) ? '是' : '否' }}</span>
            </div>
            <div class="summary-line">
              <span class="label">规则引用</span>
              <span class="value mono">{{ (provenanceSummary.rule_refs || []).join(', ') || '--' }}</span>
            </div>
            <div class="summary-line">
              <span class="label">证据引用</span>
              <span class="value mono">{{ (provenanceSummary.evidence_refs || []).join(', ') || '--' }}</span>
            </div>
          </div>
        </section>

        <section class="report-card side-card">
          <div class="section-head">
            <span class="section-kicker">原始记录</span>
            <span class="section-meta mono">{{ logs.length }}</span>
          </div>
          <div class="raw-log-stack">
            <div v-for="(log, idx) in logs" :key="`${log.timestamp}-${idx}`" class="raw-log-row">
              <div class="raw-log-head">
                <span class="raw-log-stage mono">{{ stageTitle(log.stage) }}</span>
                <span class="raw-log-time mono">{{ formatLogTime(log.timestamp) }}</span>
              </div>
              <div class="raw-log-message">{{ log.message }}</div>
            </div>
          </div>
        </section>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  getDiscoveryLogs,
  getDiscoveryResult,
  getDiscoveryStage,
  getDiscoveryStages,
  getDiscoveryTask
} from '../api/discovery'

const route = useRoute()
const taskData = ref(null)
const resultData = ref(null)
const logs = ref([])
const stagePayloads = ref({})
const stageNames = ref([])
const loading = ref(false)

const APP_HOME = '/'
const APP_WORKSPACE = '/workspace'

function stripVariantSuffix(value) {
  return String(value || '')
    .replace(/\s*[（(]改造版[）)]\s*/g, '')
    .trim()
}

function goHome() {
  window.location.href = APP_HOME
}

function goWorkspace() {
  window.location.href = APP_WORKSPACE
}

const heroTitle = computed(() => {
  if (!resultData.value) return '探索结果'
  return stripVariantSuffix(resultData.value.candidate_rules?.[0]?.rule_title || '探索结果')
})

const heroSummary = computed(() => {
  if (loading.value && !resultData.value) return '正在载入这次探索得到的结果、过程记录和校验信息。'
  return resultData.value?.summary || '当前任务尚未形成最终结果。'
})

watch(
  () => heroTitle.value,
  (value) => {
    document.title = value
      ? `结果详情 - ${value}`
      : '结果详情页'
  },
  { immediate: true }
)

function cleanCandidateTitle(value) {
  return stripVariantSuffix(value)
}

const selectedCandidate = computed(() => resultData.value?.candidate_rules?.[0] || null)
const criticCandidate = computed(() => selectedCandidate.value?.metadata?.critic_report ? selectedCandidate.value : null)
const criticRelations = computed(() => criticCandidate.value?.metadata?.critic_report?.related_rules || [])
const criticCounterexamples = computed(() => criticCandidate.value?.metadata?.critic_report?.counterexamples || [])
const criticMissing = computed(() => criticCandidate.value?.metadata?.critic_report?.missing_elements || [])
const provenanceSummary = computed(() => selectedCandidate.value?.source_provenance || {})

const stageMetrics = computed(() => {
  if (!logs.value.length) return []
  const firstPerStage = []
  const seen = new Set()
  for (const log of logs.value) {
    if (seen.has(log.stage)) continue
    seen.add(log.stage)
    firstPerStage.push(log)
  }

  return firstPerStage.map((log, index) => {
    const start = new Date(log.timestamp)
    const next = firstPerStage[index + 1] ? new Date(firstPerStage[index + 1].timestamp) : (taskData.value?.completed_at ? new Date(taskData.value.completed_at) : null)
    return {
      stage: log.stage,
      start_at: log.timestamp,
      duration_seconds: next ? Number(((next - start) / 1000).toFixed(2)) : null
    }
  })
})

const elapsedText = computed(() => {
  if (!taskData.value?.started_at) return '--'
  const start = new Date(taskData.value.started_at)
  const end = taskData.value?.completed_at ? new Date(taskData.value.completed_at) : new Date()
  const diff = Math.max(0, Math.round((end - start) / 1000))
  const minutes = Math.floor(diff / 60)
  const seconds = diff % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

const orderedStageCards = computed(() => {
  const cards = []
  const payloads = stagePayloads.value || {}
  const build = (key, title, tone, summaryBuilder, pointsBuilder) => {
    const payload = payloads[key]
    if (!payload) return
    cards.push({
      key,
      index: String(cards.length + 1).padStart(2, '0'),
      title,
      tone,
      time: metricTime(key),
      summary: summaryBuilder(payload),
      points: pointsBuilder(payload),
      raw: payload
    })
  }

  build(
    'problem_frame',
    '问题建模',
    'blue',
    (payload) => `系统先把问题与上下文折叠成结构化任务，识别实体、约束和模糊点。`,
    (payload) => [
      `意图: ${payload.intent || 'discover_rule'}`,
      `实体: ${(payload.entities || []).join(' / ') || '暂无'}`,
      `约束: ${(payload.constraints || []).join('；') || '暂无'}`,
      `模糊点: ${(payload.ambiguities || []).join('；') || '无'}`
    ]
  )
  build(
    'analogies',
    '规则类比',
    'orange',
    (payload) => '系统在规则库中寻找可直接复用、可改造或完全不相干的规则结构。',
    (payload) => [
      `直接复用: ${(payload.reuse_candidates || []).join(', ') || '无'}`,
      `可改造规则: ${(payload.adaptation_candidates || []).join(', ') || '无'}`,
      `当前缺口: ${(payload.gaps || []).join('；') || '无'}`
    ]
  )
  build(
    'evidence',
    '证据探索',
    'green',
    () => '系统从文档中提取证据片段，支持或反驳候选规则。',
    (payload) => (payload.evidence_items || []).slice(0, 4).map(item => `${item.reference || '证据'}: ${item.excerpt || item.why_relevant}`)
  )
  build(
    'candidates',
    '候选规则生成',
    'purple',
    () => '系统输出候选规则，并给出初步来源归因与分数。',
    (payload) => {
      const candidate = (payload.candidates || [])[0]
      if (!candidate) return ['暂无候选规则']
      return [
        `类型: ${displayCandidateType(candidate.candidate_type)}`,
        `标题: ${candidate.rule_title}`,
        `来源: ${(candidate.knowledge_sources || []).map(displayKnowledgeSource).join(' / ') || '暂无'}`,
        `依据度 / 涌现度: ${formatScore(candidate.grounding_score)} / ${formatScore(candidate.speculation_score)}`
      ]
    }
  )
  build(
    'validation',
    '规则审查',
    'red',
    () => '系统对候选规则做反例、关系和缺口审查。',
    (payload) => {
      const candidate = (payload.candidates || [])[0]
      if (!candidate) return ['暂无验证结果']
      return [
      `状态: ${displayValidationStatus(candidate.validation_status)}`,
      `原因: ${candidate.validation_reason}`,
      `关联: ${(candidate.critic_report?.related_rules || []).map(item => `${item.rule_id}:${displayRelationType(item.relation_type)}`).join(' / ') || '无'}`,
      `反例: ${(candidate.critic_report?.counterexamples || []).join('；') || '无'}`
      ]
    }
  )
  return cards
})

function metricTime(stage) {
  const metric = stageMetrics.value.find(item => item.stage === stage)
  return metric ? formatLogTime(metric.start_at) : '--'
}

function stageTitle(stage) {
  return {
    start: '启动',
    problem_frame: '问题建模',
    analogies: '规则类比',
    evidence: '证据探索',
    candidates: '候选规则生成',
    validation: '规则审查',
    decision: '最终综合'
  }[stage] || stage
}

function displayMode(value) {
  return {
    grounded: '闭卷模式',
    emergent: '涌现模式'
  }[value] || value || '--'
}

function displayResolution(value) {
  return {
    adapted_rule: '改造旧规则',
    exact_reuse: '直接复用旧规则',
    novel_rule: '形成新规则',
    insufficient_evidence: '证据不足'
  }[value] || value || '--'
}

function displayTaskStatus(value) {
  return {
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    timed_out: '已超时',
    need_human_review: '待人工复核',
    insufficient_evidence: '证据不足',
    pending: '处理中',
    running: '处理中'
  }[value] || value || '--'
}

function displayValidationStatus(value) {
  return {
    provisionally_supported: '初步支持',
    weakly_supported: '支持较弱',
    supported: '支持当前结果',
    rejected: '驳回'
  }[value] || value || '--'
}

function displayCandidateType(value) {
  return {
    adapted_rule: '改造规则',
    exact_reuse: '直接复用',
    novel_rule: '新规则'
  }[value] || value || '--'
}

function displayKnowledgeSource(value) {
  return {
    rule_library: '规则库',
    document_evidence: '文档证据',
    general_knowledge: '通用知识'
  }[value] || value || '--'
}

function displayRelationType(value) {
  return {
    supplement: '补充',
    conflict: '冲突',
    duplicate: '重复',
    tighten: '收紧',
    analogous: '类比'
  }[value] || value || '--'
}

function formatScore(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '--'
  return Number(value).toFixed(2)
}

function formatLogTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
}

function formatJson(value) {
  return JSON.stringify(value, null, 2)
}

async function refreshAll() {
  const taskId = route.params.taskId
  if (!taskId) return
  loading.value = true
  try {
    const [taskRes, resultRes, logsRes, stagesRes] = await Promise.all([
      getDiscoveryTask(taskId),
      getDiscoveryResult(taskId),
      getDiscoveryLogs(taskId, 0),
      getDiscoveryStages(taskId)
    ])

    taskData.value = taskRes.data
    resultData.value = resultRes.data
    logs.value = logsRes.data.logs || []
    stageNames.value = stagesRes.data.stages || []

    const entries = await Promise.all(
      stageNames.value.map(async (stage) => {
        const stageRes = await getDiscoveryStage(taskId, stage)
        return [stage, stageRes.data.payload]
      })
    )
    stagePayloads.value = Object.fromEntries(entries)
  } catch (error) {
    console.error('加载 discovery report 失败:', error)
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.taskId,
  () => {
    refreshAll()
  },
  { immediate: true }
)

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.discovery-report-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(161, 75, 43, 0.08), transparent 24%),
    radial-gradient(circle at 82% 10%, rgba(16, 39, 61, 0.1), transparent 24%),
    radial-gradient(circle at bottom left, rgba(29, 111, 116, 0.08), transparent 30%),
    #f6f2e8;
  color: #0d1317;
  font-family: 'Avenir Next', 'Noto Sans SC', sans-serif;
}

.report-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 22px;
  border: 1px solid rgba(13, 19, 23, 0.12);
  background: rgba(255, 252, 247, 0.88);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 10px;
  z-index: 20;
  margin: 10px 10px 0;
  border-radius: 22px;
  box-shadow: 0 20px 44px rgba(13, 19, 23, 0.06);
}

.report-header-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 18px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  min-width: max-content;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #10273d, #1b4163);
  color: #fff;
  font-weight: 800;
  font-family: 'Iowan Old Style', 'Noto Serif SC', serif;
  font-size: 19px;
}

.brand-copy small {
  display: block;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #8a4a2d;
}

.brand-copy strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
}

.eyebrow {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: #6d655a;
  margin-bottom: 10px;
}

.report-title {
  font-size: 34px;
  line-height: 1.05;
  margin-bottom: 10px;
}

.report-summary {
  max-width: 860px;
  line-height: 1.7;
  color: #3a454e;
}

.report-header-right {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.nav-btn {
  border: 1px solid rgba(16, 39, 61, 0.12);
  border-radius: 999px;
  padding: 10px 14px;
  background: rgba(16, 39, 61, 0.07);
  color: #10273d;
  font-weight: 700;
  cursor: pointer;
}

.nav-btn:not(.ghost) {
  background: linear-gradient(135deg, #10273d, #1b4163);
  color: #fff;
  border-color: rgba(16, 39, 61, 0.22);
}

.nav-btn.ghost {
  background: rgba(13, 19, 23, 0.08);
  color: #0d1317;
}

.report-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) 360px;
  gap: 22px;
  padding: 22px;
}

.report-main,
.report-side {
  min-width: 0;
}

.report-main {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-side {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-card {
  border: 1px solid rgba(13, 19, 23, 0.12);
  background: rgba(255, 255, 255, 0.72);
  border-radius: 22px;
  padding: 20px;
  box-shadow: 0 18px 35px rgba(13, 19, 23, 0.05);
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #6d655a;
}

.section-meta {
  color: #6d655a;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.summary-item {
  border-radius: 18px;
  padding: 14px;
  background: rgba(246, 242, 232, 0.9);
}

.summary-label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  color: #6d655a;
  margin-bottom: 8px;
}

.summary-value {
  font-weight: 800;
  font-size: 16px;
}

.brief-block + .brief-block {
  margin-top: 14px;
}

.brief-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #6d655a;
  margin-bottom: 8px;
}

.brief-text {
  line-height: 1.7;
  color: #233039;
}

.candidate-stack,
.trail-stack,
.ledger-stack,
.raw-log-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.candidate-card,
.trail-card,
.critic-box,
.ledger-row,
.raw-log-row {
  border: 1px solid rgba(13, 19, 23, 0.1);
  border-radius: 18px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.8);
}

.candidate-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.candidate-title {
  font-size: 20px;
  font-weight: 800;
}

.candidate-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #6d655a;
  font-family: 'JetBrains Mono', monospace;
}

.score-pair {
  display: flex;
  gap: 10px;
}

.score-box {
  min-width: 72px;
  text-align: right;
}

.score-name {
  display: block;
  font-size: 11px;
  color: #6d655a;
}

.score-value {
  font-size: 14px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.candidate-rule-text {
  line-height: 1.75;
  color: #1b2329;
  margin-bottom: 12px;
}

.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.chip {
  font-size: 11px;
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(29, 111, 116, 0.12);
  color: #1d6f74;
}

.reasoning-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reason-line {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px;
}

.reason-label {
  font-size: 12px;
  color: #6d655a;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.reason-text {
  line-height: 1.6;
}

.trail-card {
  position: relative;
}

.trail-blue { border-left: 5px solid #2855a6; }
.trail-orange { border-left: 5px solid #c66318; }
.trail-green { border-left: 5px solid #3c7a40; }
.trail-purple { border-left: 5px solid #6a3bb8; }
.trail-red { border-left: 5px solid #a43232; }

.trail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.trail-title-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.trail-index,
.ledger-duration,
.ledger-time,
.raw-log-time,
.raw-log-stage {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #6d655a;
}

.trail-title {
  font-weight: 800;
}

.trail-summary {
  line-height: 1.75;
  margin-bottom: 12px;
}

.trail-points {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trail-point {
  line-height: 1.65;
  color: #243038;
}

.trail-raw {
  margin-top: 12px;
}

.trail-raw summary {
  cursor: pointer;
  color: #6d655a;
  font-size: 12px;
}

.trail-raw pre {
  margin-top: 8px;
  padding: 12px;
  border-radius: 14px;
  background: #101418;
  color: #eff3ec;
  overflow: auto;
  font-size: 12px;
  line-height: 1.55;
}

.critic-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.critic-title,
.block-title {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #6d655a;
  margin-bottom: 10px;
}

.critic-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.critic-item-head,
.ledger-row-head,
.raw-log-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.critic-rule,
.ledger-stage {
  font-weight: 700;
}

.critic-type {
  font-size: 11px;
  color: #6d655a;
  text-transform: uppercase;
}

.critic-reason,
.open-line,
.reject-text,
.raw-log-message {
  line-height: 1.65;
  color: #233039;
}

.empty-mini,
.empty-panel {
  color: #6d655a;
  line-height: 1.7;
}

.open-block + .open-block {
  margin-top: 18px;
}

.open-line,
.reject-line {
  padding: 10px 0;
  border-top: 1px dashed rgba(13, 19, 23, 0.08);
}

.reject-line {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 12px;
}

.reject-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #6e2d39;
}

.provenance-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-line {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px;
}

.label {
  font-size: 12px;
  color: #6d655a;
  text-transform: uppercase;
}

.value {
  font-family: 'JetBrains Mono', monospace;
  word-break: break-word;
}

.raw-log-stack {
  max-height: calc(100vh - 280px);
  overflow: auto;
  padding-right: 4px;
}

@media (max-width: 1280px) {
  .report-shell,
  .summary-grid,
  .critic-grid,
  .reason-line {
    grid-template-columns: 1fr;
  }

  .report-header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }
}

@media (max-width: 760px) {
  .report-header {
    padding: 20px;
    flex-direction: column;
    margin: 8px;
  }

  .report-shell {
    padding: 16px;
  }

  .candidate-head {
    flex-direction: column;
  }
}
</style>
