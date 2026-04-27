<template>
  <div class="discovery-workbench" :class="{ 'embed-mode': embedMode }">
    <header v-if="!embedMode" class="page-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">多智能体规则发现 / 工作台</div>
        <div class="mode-strip">
          <button
            v-for="item in modeOptions"
            :key="item.value"
            class="mode-pill"
            :class="{ active: form.discoveryMode === item.value }"
            @click="form.discoveryMode = item.value"
          >
            <span class="mode-name">{{ item.label }}</span>
            <span class="mode-hint">{{ item.hint }}</span>
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="header-stat">
          <span class="stat-label">任务</span>
          <span class="stat-value mono">{{ activeTaskId || '暂无' }}</span>
        </div>
        <div class="header-stat">
          <span class="stat-label">状态</span>
          <span class="stat-value status-pill" :class="`status-${statusTone}`">{{ statusText }}</span>
        </div>
      </div>
    </header>

    <main class="page-body">
      <aside v-if="!embedMode" class="control-panel">
        <section class="panel-card intro-card">
          <div class="card-topline">规则发现工作台</div>
          <h1 class="card-title">多智能体规则发现工作台</h1>
          <p class="card-desc">
            输入规则库、文档、问题与上下文，实时查看问题建模、规则类比、证据探索、候选规则生成、规则审查与最终综合如何逐步形成候选规则。
          </p>
          <div class="intro-actions">
            <button class="ghost-btn" @click="loadDemoPreset('grounded')">载入闭卷样例</button>
            <button class="ghost-btn" @click="loadDemoPreset('emergent')">载入涌现样例</button>
          </div>
          <div class="hero-cta-row">
            <button class="hero-run-btn" :disabled="submitting || !canSubmit" @click="startDiscovery">
              <span v-if="!submitting">立即运行规则发现</span>
              <span v-else>初始化中...</span>
            </button>
          </div>
        </section>

        <section class="panel-card">
          <div class="section-head">
            <span class="section-index mono">01</span>
            <span class="section-title">规则库</span>
          </div>
          <div class="rule-list">
            <div v-for="(rule, index) in form.rules" :key="index" class="rule-editor">
              <div class="rule-editor-head">
                <span class="rule-badge mono">R{{ String(index + 1).padStart(2, '0') }}</span>
                <button v-if="form.rules.length > 1" class="mini-remove" @click="removeRule(index)">移除</button>
              </div>
              <input v-model="rule.title" class="text-input" placeholder="规则标题" />
              <textarea v-model="rule.content" class="text-area compact" placeholder="规则正文" rows="4"></textarea>
              <div class="inline-grid">
                <input v-model="rule.conditionsText" class="text-input" placeholder="适用条件，用 / 分隔" />
                <input v-model="rule.source" class="text-input" placeholder="规则来源" />
              </div>
            </div>
          </div>
          <button class="add-row-btn" @click="addRule">+ 添加规则</button>
        </section>

        <section class="panel-card">
          <div class="section-head">
            <span class="section-index mono">02</span>
            <span class="section-title">文档证据</span>
          </div>
          <div class="doc-list">
            <div v-for="(doc, index) in form.documents" :key="index" class="doc-editor">
              <div class="rule-editor-head">
                <span class="rule-badge mono">D{{ String(index + 1).padStart(2, '0') }}</span>
                <button v-if="form.documents.length > 1" class="mini-remove" @click="removeDocument(index)">移除</button>
              </div>
              <input v-model="doc.title" class="text-input" placeholder="文档标题" />
              <textarea v-model="doc.content" class="text-area" placeholder="文档内容" rows="5"></textarea>
            </div>
          </div>
          <button class="add-row-btn" @click="addDocument">+ 添加文档</button>
        </section>

        <section class="panel-card">
          <div class="section-head">
            <span class="section-index mono">03</span>
            <span class="section-title">问题定义</span>
          </div>
          <textarea v-model="form.query" class="text-area compact" placeholder="问题" rows="3"></textarea>
          <textarea v-model="form.context" class="text-area" placeholder="上下文" rows="5"></textarea>
          <div class="option-grid">
            <label class="toggle-box">
              <input v-model="form.useLlm" type="checkbox" />
              <span>启用 LLM</span>
            </label>
            <label class="toggle-box">
              <input v-model="form.deduplicate" type="checkbox" />
              <span>任务去重</span>
            </label>
          </div>
          <div class="option-grid">
            <div class="slider-box">
              <span class="slider-label">超时时间</span>
              <input v-model.number="form.timeoutSeconds" type="range" min="30" max="240" step="15" />
              <span class="slider-value mono">{{ form.timeoutSeconds }}s</span>
            </div>
          </div>
          <div class="cta-row">
            <button class="primary-btn" :disabled="submitting || !canSubmit" @click="startDiscovery">
              <span v-if="!submitting">启动规则发现</span>
              <span v-else>初始化中...</span>
            </button>
            <button class="secondary-btn" :disabled="!canRerun" @click="rerunTask">重新运行</button>
            <button class="secondary-btn danger" :disabled="!canCancel" @click="cancelTaskRun">取消任务</button>
          </div>
        </section>

        <section v-if="resultData" class="panel-card result-card">
          <div class="section-head">
            <span class="section-index mono">04</span>
            <span class="section-title">发现结果</span>
          </div>
          <div class="result-actions">
            <button class="secondary-btn" @click="openReport">打开发现报告页</button>
          </div>
          <div class="result-headline">
            <span class="result-tag">{{ displayMode(resultData.discovery_mode) }}</span>
            <span class="result-tag result-tag--accent">{{ displayResolution(resultData.resolution_type) }}</span>
          </div>
          <p class="result-summary">{{ resultData.summary }}</p>
          <div v-if="resultData.resolution_type === 'insufficient_evidence' && resultData.candidate_rules?.length" class="exploration-banner">
            当前没有形成可直接采纳的规则，以下内容作为探索性产物保留，供继续补证与人工研究。
          </div>
          <div v-if="selectedCandidate" class="comparison-board">
            <div
              v-for="panel in comparisonPanels"
              :key="panel.key"
              class="comparison-card"
              :class="`comparison-${panel.tone}`"
            >
              <div class="comparison-kicker">{{ panel.kicker }}</div>
              <div class="comparison-title">{{ panel.title }}</div>
              <div class="comparison-subtitle mono">{{ panel.subtitle }}</div>
              <div v-if="panel.body" class="comparison-body">{{ panel.body }}</div>
              <div v-if="panel.points?.length" class="comparison-points">
                <div v-for="(point, idx) in panel.points" :key="idx" class="comparison-point">{{ point }}</div>
              </div>
              <div v-if="panel.chips?.length" class="comparison-chips">
                <span v-for="chip in panel.chips" :key="chip" class="comparison-chip">{{ chip }}</span>
              </div>
            </div>
          </div>
          <div v-if="resultData.candidate_rules?.length" class="candidate-list">
            <div v-for="candidate in resultData.candidate_rules" :key="candidate.candidate_id" class="candidate-card">
              <div class="candidate-top">
                <div>
                  <div class="candidate-title">{{ candidate.rule_title }}</div>
                  <div class="candidate-meta mono">{{ displayCandidateType(candidate.candidate_type) }} / {{ displayValidationStatus(candidate.validation_status) }}</div>
                </div>
                <div class="score-cluster">
                  <div class="score-item">
                    <span class="score-label">依据度</span>
                    <span class="score-value mono">{{ formatScore(candidate.grounding_score) }}</span>
                  </div>
                  <div class="score-item">
                    <span class="score-label">涌现度</span>
                    <span class="score-value mono">{{ formatScore(candidate.speculation_score) }}</span>
                  </div>
                </div>
              </div>
              <p class="candidate-text">{{ candidate.rule_text }}</p>
              <div class="provenance-row">
                <span v-for="source in candidate.knowledge_sources || []" :key="source" class="source-chip">
                  {{ displayKnowledgeSource(source) }}
                </span>
              </div>
            </div>
          </div>
          <div v-if="resultData.open_questions?.length" class="open-questions">
            <div class="subheading">待解决问题</div>
            <div v-for="(item, idx) in resultData.open_questions" :key="idx" class="question-line">
              {{ item }}
            </div>
          </div>
          <div v-if="resultData.rejected_candidates?.length" class="rejected-block">
            <div class="subheading">驳回与阻塞</div>
            <div v-for="(item, idx) in resultData.rejected_candidates" :key="idx" class="rejected-line">
              <div class="rejected-id mono">{{ item.candidate_id || `reason-${idx + 1}` }}</div>
              <div class="rejected-reason">{{ item.reason }}</div>
            </div>
          </div>
        </section>
      </aside>

      <section class="analysis-panel">
        <div class="analysis-top">
          <div class="workflow-band">
            <div
              v-for="step in workflowSteps"
              :key="step.key"
              class="workflow-node"
              :class="`node-${step.state}`"
            >
              <div class="node-dot"></div>
              <div class="node-body">
                <div class="node-title-row">
                  <span class="node-index mono">{{ step.index }}</span>
                  <span class="node-title">{{ step.title }}</span>
                </div>
                <div class="node-meta mono">{{ step.meta }}</div>
              </div>
            </div>
          </div>

          <div class="metric-board">
            <div class="metric-card">
              <span class="metric-name">模式</span>
              <span class="metric-data mono">{{ displayMode(currentMode) }}</span>
            </div>
            <div class="metric-card">
              <span class="metric-name">进度</span>
              <span class="metric-data mono">{{ taskData?.progress ?? 0 }}%</span>
            </div>
            <div class="metric-card">
              <span class="metric-name">参与角色</span>
              <span class="metric-data mono">{{ discussionCards.length }}</span>
            </div>
            <div class="metric-card">
              <span class="metric-name">耗时</span>
              <span class="metric-data mono">{{ elapsedText }}</span>
            </div>
          </div>

          <div class="agent-radar">
            <div class="panel-title-row">
              <span class="panel-kicker">角色雷达</span>
              <span class="panel-note mono">{{ activeAgentNames.length }} 个活跃</span>
            </div>
            <div class="radar-copy">
              小圆点代表当前系统中的角色。亮起表示正在行动，常亮表示已参与，暗色表示尚未进入本轮讨论。
            </div>
            <div class="agent-orbit">
              <div
                v-for="agent in agentRadarAgents"
                :key="agent.name"
                class="orbit-agent"
                :class="[`orbit-${agent.state}`, `orbit-tone-${agent.tone}`]"
                :title="agent.name"
              >
                <span class="orbit-dot"></span>
                <span class="orbit-label mono">{{ agent.short }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="conversation-layout">
          <div class="discussion-column">
            <div class="panel-title-row">
              <span class="panel-kicker">多智能体讨论区</span>
              <span class="panel-note mono">{{ activeTaskId || '暂无任务' }}</span>
            </div>
            <div ref="discussionFeedRef" class="discussion-feed">
              <div v-if="discussionCards.length === 0" class="empty-state">
                <div class="empty-title">等待多智能体启动</div>
                <div class="empty-copy">提交任务后，这里会依次出现问题建模、规则类比、证据探索、候选规则生成、规则审查和最终综合的讨论卡片。</div>
              </div>

              <TransitionGroup name="card-flow" tag="div" class="discussion-stack">
                <div
                  v-for="(card, cardIndex) in visibleDiscussionCards"
                  :key="card.key"
                  class="agent-card"
                  :class="[`agent-${card.tone}`, { 'agent-live': card.isLive }]"
                  :style="{ '--card-delay': `${cardIndex * 80}ms` }"
                >
                  <div class="agent-top">
                    <div class="agent-avatar">{{ card.avatar }}</div>
                    <div class="agent-meta">
                      <div class="agent-name">{{ card.agent }}</div>
                      <div class="agent-stage mono">{{ card.stage }}</div>
                    </div>
                    <div class="agent-time-cluster">
                      <div v-if="card.isLive" class="agent-live-indicator">
                        <span></span><span></span><span></span>
                      </div>
                      <div class="agent-time mono">{{ card.timestamp }}</div>
                    </div>
                  </div>
                  <div class="agent-headline">{{ card.headline }}</div>
                  <div v-if="card.points?.length" class="agent-points">
                    <div
                      v-for="(point, index) in card.points"
                      :key="index"
                      class="point-line"
                      :style="{ '--point-delay': `${cardIndex * 80 + index * 90}ms` }"
                    >
                      {{ point }}
                    </div>
                  </div>
                  <details class="agent-raw">
                    <summary>查看原始产物</summary>
                    <pre>{{ formatJson(card.raw) }}</pre>
                  </details>
                </div>
              </TransitionGroup>
            </div>
          </div>

          <div class="evidence-column">
            <div class="panel-title-row">
              <span class="panel-kicker">阶段台账</span>
              <span class="panel-note mono">{{ stageMetrics.length }} 个阶段</span>
            </div>
            <div class="ledger-list">
              <div v-for="item in stageMetrics" :key="item.stage" class="ledger-item">
                <div class="ledger-head">
                  <span class="ledger-stage">{{ stageTitle(item.stage) }}</span>
                  <span class="ledger-duration mono">{{ item.duration_seconds ?? '--' }}s</span>
                </div>
                <div class="ledger-time mono">{{ item.start_at }}</div>
              </div>
            </div>

            <div class="panel-title-row panel-title-row--spaced">
              <span class="panel-kicker">原始日志</span>
              <span class="panel-note mono">{{ logs.length }}</span>
            </div>
            <div class="log-list">
              <div v-for="(log, idx) in logs" :key="`${log.timestamp}-${idx}`" class="log-line">
                <div class="log-head">
                  <span class="log-stage mono">{{ stageTitle(log.stage) }}</span>
                  <span class="log-time mono">{{ formatLogTime(log.timestamp) }}</span>
                </div>
                <div class="log-message">{{ log.message }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  cancelDiscoveryTask,
  createDiscoveryTask,
  getDiscoveryLogs,
  getDiscoveryResult,
  getDiscoveryStage,
  getDiscoveryStages,
  getDiscoveryTask,
  importDocuments,
  importRuleSet,
  rerunDiscoveryTask
} from '../api/discovery'

const router = useRouter()
const route = useRoute()

const defaultRule = () => ({
  title: '',
  content: '',
  conditionsText: '',
  source: ''
})

const defaultDocument = () => ({
  title: '',
  content: ''
})

const createGroundedPreset = () => ({
  discoveryMode: 'grounded',
  useLlm: true,
  deduplicate: true,
  timeoutSeconds: 120,
  query: '面对即将发布且表述模糊的重大公告，应适用什么规则？',
  context: '公告涉及重大合作变化，当前表述较模糊，可能误导外部。',
  rules: [
    {
      title: '披露义务规则',
      content: '当公司发布重大事项信息时，应及时披露相关事实。',
      conditionsText: '公司发布重大事项信息',
      source: '规则手册'
    },
    {
      title: '补充说明规则',
      content: '当公开信息存在歧义时，应提供补充说明以避免误导。',
      conditionsText: '公开信息存在歧义',
      source: '规则手册'
    }
  ],
  documents: [
    {
      title: '公告草稿',
      content: '公司计划在下周发布一则涉及重大合作变化的公告，但当前表述较模糊，可能引发误解。'
    }
  ]
})

const createEmergentPreset = () => ({
  discoveryMode: 'emergent',
  useLlm: true,
  deduplicate: true,
  timeoutSeconds: 120,
  query: '对于AI自动生成的对外合作邮件草稿，在发送前应适用什么规则？',
  context: 'AI草稿可能夸大合作确定性，并写入未确认的交付时间；如果未经人工复核直接发送，容易形成对外误导。',
  rules: [
    {
      title: 'Branch Naming Policy',
      content: 'All source code branches must follow the naming convention feature/* or fix/* before merge.',
      conditionsText: 'source code branch management',
      source: 'engineering-policy'
    }
  ],
  documents: [
    {
      title: '内部纪要',
      content: '近期团队开始尝试由AI自动生成对外合作邮件草稿。草稿常会夸大合作确定性，甚至默认写入未确认的交付时间。'
    }
  ]
})

const form = reactive(createGroundedPreset())
const submitting = ref(false)
const activeTaskId = ref('')
const taskData = ref(null)
const resultData = ref(null)
const logs = ref([])
const stagePayloads = reactive({})
const stageNames = ref([])
const logCursor = ref(0)
const pollHandle = ref(null)
const discussionFeedRef = ref(null)
const submittedRules = ref([])
const revealedCardKeys = ref([])
const revealTimers = ref([])

const modeOptions = [
  { value: 'grounded', label: '闭卷模式', hint: '只基于输入材料' },
  { value: 'emergent', label: '涌现模式', hint: '允许通用知识参与' }
]

const embedMode = computed(() => String(route.query.embed || '') === '1')

const AGENT_RADAR_REGISTRY = [
  { name: 'Intent Mapper', short: 'IM', tone: 'blue' },
  { name: 'Constraint Extractor', short: 'CE', tone: 'teal' },
  { name: 'Ambiguity Mapper', short: 'AM', tone: 'orange' },
  { name: 'Exact Match Scout', short: 'XS', tone: 'green' },
  { name: 'Adaptation Scout', short: 'AS', tone: 'purple' },
  { name: 'Negative Miner', short: 'NM', tone: 'red' },
  { name: 'Support Finder', short: 'SF', tone: 'green' },
  { name: 'Risk Finder', short: 'RF', tone: 'orange' },
  { name: 'Gap Finder', short: 'GF', tone: 'red' },
  { name: 'Reuse Drafter', short: 'RD', tone: 'blue' },
  { name: 'Adaptation Drafter', short: 'AD', tone: 'teal' },
  { name: 'Novel Rule Drafter', short: 'ND', tone: 'wine' },
  { name: 'Conflict Critic', short: 'CC', tone: 'red' },
  { name: 'Counterexample Critic', short: 'XC', tone: 'orange' },
  { name: 'Provenance Critic', short: 'PC', tone: 'purple' },
  { name: 'Decision Synthesizer', short: 'DS', tone: 'black' }
]

const stageOrder = ['problem_frame', 'analogies', 'evidence', 'candidates', 'validation']

const canSubmit = computed(() => {
  return form.query.trim() && form.context.trim() && form.rules.some(rule => rule.title.trim() && rule.content.trim()) && form.documents.some(doc => doc.title.trim() && doc.content.trim())
})

const currentMode = computed(() => {
  return resultData.value?.discovery_mode || taskData.value?.discovery_mode || form.discoveryMode
})

const statusText = computed(() => {
  const value = taskData.value?.status
  if (!value) return '未启动'
  return displayTaskStatus(value)
})

const statusTone = computed(() => {
  const value = taskData.value?.status
  if (!value) return '未启动'
  if (['failed', 'timed_out', 'cancelled'].includes(value)) return 'error'
  if (['completed', 'need_human_review', 'insufficient_evidence'].includes(value)) return 'done'
  return 'active'
})

const workflowSteps = computed(() => {
  const currentStage = taskData.value?.current_stage || 'received'
  return [
    { key: 'problem_frame', index: '01', title: '问题建模', state: stateForStage('problem_frame', currentStage), meta: stageMeta('problem_frame') },
    { key: 'analogies', index: '02', title: '规则类比', state: stateForStage('analogies', currentStage), meta: stageMeta('analogies') },
    { key: 'evidence', index: '03', title: '证据探索', state: stateForStage('evidence', currentStage), meta: stageMeta('evidence') },
    { key: 'candidates', index: '04', title: '候选规则生成', state: stateForStage('candidates', currentStage), meta: stageMeta('candidates') },
    { key: 'validation', index: '05', title: '规则审查', state: stateForStage('validation', currentStage), meta: stageMeta('validation') },
    { key: 'decision', index: '06', title: '最终综合', state: resultData.value ? 'done' : stateForStage('decision', currentStage), meta: resultData.value?.resolution_type ? displayResolution(resultData.value.resolution_type) : '待处理' }
  ]
})

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

const discussionCards = computed(() => {
  const cards = []
  const buildAgentRunCards = (stage, payload) => {
    const agentRuns = payload?.agent_runs || []
    return agentRuns.map((run, index) => ({
      key: `${stage}-${index}-${run.agent_name}`,
      agent: run.agent_name || stageTitle(stage),
      avatar: (run.agent_name || stageTitle(stage)).slice(0, 1),
      tone: run.tone || 'blue',
      isLive: taskData.value?.current_stage === stage && !resultData.value,
      stage,
      timestamp: timestampForStage(stage),
        headline: run.headline || `${stageTitle(stage)}正在处理中。`,
      points: run.points || [],
      raw: run.raw || payload
    }))
  }

  const buildFallbackCard = (stage, payload) => {
    if (!payload) return null
    if (stage === 'problem_frame') {
      return {
        key: stage,
        agent: '问题建模',
        avatar: 'P',
        tone: 'blue',
        isLive: taskData.value?.current_stage === stage && !resultData.value,
        stage,
        timestamp: timestampForStage(stage),
        headline: '先把问题与上下文折叠成结构化任务。',
        points: [
          `意图: ${payload.intent || 'discover_rule'}`,
          `实体: ${(payload.entities || []).join(' / ') || '暂无'}`,
          `约束: ${(payload.constraints || []).join('；') || '暂无'}`,
          `模糊点: ${(payload.ambiguities || []).join('；') || '无'}`
        ],
        raw: payload
      }
    }
    if (stage === 'analogies') {
      return {
        key: stage,
        agent: '规则类比',
        avatar: 'A',
        tone: 'orange',
        isLive: taskData.value?.current_stage === stage && !resultData.value,
        stage,
        timestamp: timestampForStage(stage),
        headline: '从规则库里找可复用、可改造、或根本不相干的旧规则。',
        points: [
          `直接复用: ${(payload.reuse_candidates || []).join(', ') || '无'}`,
          `可改造规则: ${(payload.adaptation_candidates || []).join(', ') || '无'}`,
          `当前缺口: ${(payload.gaps || []).join('；') || '无'}`
        ],
        raw: payload
      }
    }
    if (stage === 'evidence') {
      return {
        key: stage,
        agent: '证据探索',
        avatar: 'E',
        tone: 'green',
        isLive: taskData.value?.current_stage === stage && !resultData.value,
        stage,
        timestamp: timestampForStage(stage),
        headline: '把文档片段拉进讨论，给候选规则补证。',
        points: (payload.evidence_items || []).slice(0, 3).map(item => `${item.reference || '证据'}: ${item.excerpt || item.why_relevant}`),
        raw: payload
      }
    }
    if (stage === 'candidates') {
      const candidate = (payload.candidates || [])[0]
      return {
        key: stage,
        agent: '候选规则生成',
        avatar: 'H',
        tone: 'purple',
        isLive: taskData.value?.current_stage === stage && !resultData.value,
        stage,
        timestamp: timestampForStage(stage),
        headline: '形成候选规则，并给出初步来源归因。',
        points: candidate ? [
        `类型: ${displayCandidateType(candidate.candidate_type)}`,
        `标题: ${candidate.rule_title}`,
        `来源: ${(candidate.knowledge_sources || []).map(displayKnowledgeSource).join(' / ') || '暂无'}`,
        `依据度 / 涌现度: ${formatScore(candidate.grounding_score)} / ${formatScore(candidate.speculation_score)}`
      ] : ['暂无候选规则'],
        raw: payload
      }
    }
    if (stage === 'validation') {
      const candidate = (payload.candidates || [])[0]
      return {
        key: stage,
        agent: '规则审查',
        avatar: 'C',
        tone: 'red',
        isLive: taskData.value?.current_stage === stage && !resultData.value,
        stage,
        timestamp: timestampForStage(stage),
        headline: '找反例、找冲突、找边界，决定该不该放行。',
        points: candidate ? [
          `状态: ${displayValidationStatus(candidate.validation_status)}`,
          `原因: ${candidate.validation_reason}`,
          `关联: ${(candidate.critic_report?.related_rules || []).map(item => `${item.rule_id}:${displayRelationType(item.relation_type)}`).join(' / ') || '无'}`,
          `反例: ${(candidate.critic_report?.counterexamples || []).join('；') || '无'}`
        ] : ['暂无验证结果'],
        raw: payload
      }
    }
    return null
  }

  for (const stage of stageOrder) {
    const payload = stagePayloads[stage]
    const runCards = buildAgentRunCards(stage, payload)
    if (runCards.length) {
      cards.push(...runCards)
      continue
    }
    const card = buildFallbackCard(stage, payload)
    if (card) cards.push(card)
  }

  if (resultData.value) {
    cards.push({
      key: 'decision',
      agent: '最终综合',
      avatar: 'D',
      tone: 'black',
      isLive: false,
      stage: 'decision',
      timestamp: taskData.value?.completed_at ? formatLogTime(taskData.value.completed_at) : '--',
      headline: '整合全部讨论，给出最终规则发现结论。',
      points: [
        `模式: ${displayMode(resultData.value.discovery_mode)}`,
        `结论类型: ${displayResolution(resultData.value.resolution_type)}`,
        `需人工复核: ${String(resultData.value.need_human_review)}`,
        `总结: ${resultData.value.summary}`
      ],
      raw: resultData.value
    })
  }

  return cards
})

const activeAgentNames = computed(() => {
  return visibleDiscussionCards.value
    .filter(card => card.isLive)
    .map(card => card.agent)
})

const completedAgentNames = computed(() => {
  return Array.from(new Set(discussionCards.value.map(card => card.agent)))
})

const agentRadarAgents = computed(() => {
  return AGENT_RADAR_REGISTRY.map((agent) => {
    let state = 'idle'
    if (activeAgentNames.value.includes(agent.name)) {
      state = 'active'
    } else if (completedAgentNames.value.includes(agent.name)) {
      state = 'seen'
    }
    return {
      ...agent,
      state
    }
  })
})

const visibleDiscussionCards = computed(() => {
  return discussionCards.value.filter(card => revealedCardKeys.value.includes(card.key))
})

const selectedCandidate = computed(() => {
  return resultData.value?.candidate_rules?.[0] || null
})

const existingRuleReference = computed(() => {
  if (!selectedCandidate.value) return null
  const snapshot = submittedRules.value || []
  const ids = [selectedCandidate.value.rule_id, ...(selectedCandidate.value.derived_from || [])].filter(Boolean)
  const related = selectedCandidate.value.metadata?.critic_report?.related_rules || []
  for (const id of ids) {
    const hit = snapshot.find(item => item.rule_id === id)
    if (hit) return hit
  }
  const firstRelated = related.find(item => item.rule_id)
  if (firstRelated) {
    const hit = snapshot.find(item => item.rule_id === firstRelated.rule_id)
    if (hit) return hit
    return {
      rule_id: firstRelated.rule_id,
      title: firstRelated.title,
      content: '',
      conditions: [],
      source: '',
      relation_type: firstRelated.relation_type,
      relation_reason: firstRelated.relation_reason
    }
  }
  return null
})

const comparisonPanels = computed(() => {
  if (!selectedCandidate.value) return []
  const candidate = selectedCandidate.value
  const existing = existingRuleReference.value
  const criticRelated = candidate.metadata?.critic_report?.related_rules || []
  const relationLine = criticRelated.length
    ? criticRelated.map(item => `${item.rule_id}:${item.relation_type}`).join(' / ')
    : '无关联旧规则'

  return [
    {
      key: 'existing',
      kicker: '现有规则',
      title: existing?.title || '本轮未找到直接对应旧规则',
      subtitle: existing?.rule_id || '规则库',
      body: existing?.content || '当前候选规则没有直接绑定的旧规则文本。',
      points: existing ? [
        `适用条件: ${(existing.conditions || []).join('；') || '暂无'}`,
        `规则来源: ${existing.source || '暂无'}`,
        existing.relation_reason ? `关联说明: ${existing.relation_reason}` : `关系映射: ${relationLine}`
      ] : ['系统未在规则库中锁定直接来源规则。'],
      chips: existing?.relation_type ? [existing.relation_type] : [],
      tone: 'sand'
    },
    {
      key: 'adapted',
      kicker: '改造与复用',
      title: ['adapted_rule', 'exact_reuse'].includes(candidate.candidate_type) ? candidate.rule_title : '本轮未走改造/复用路径',
      subtitle: ['adapted_rule', 'exact_reuse'].includes(candidate.candidate_type) ? displayCandidateType(candidate.candidate_type) : '未激活',
      body: ['adapted_rule', 'exact_reuse'].includes(candidate.candidate_type) ? candidate.rule_text : '当前结果不属于复用或改造已有规则。',
      points: ['adapted_rule', 'exact_reuse'].includes(candidate.candidate_type) ? [
        `改造说明: ${candidate.adaptation_note || '暂无'}`,
        `验证状态: ${displayValidationStatus(candidate.validation_status)}`,
        `依据度 / 涌现度: ${formatScore(candidate.grounding_score)} / ${formatScore(candidate.speculation_score)}`
      ] : ['如果后续出现 exact_reuse 或 adapted_rule，这里会显示规则如何从旧规则演化。'],
      chips: ['adapted_rule', 'exact_reuse'].includes(candidate.candidate_type) ? (candidate.knowledge_sources || []) : [],
      tone: 'teal'
    },
    {
      key: 'novel',
      kicker: '全新规则',
      title: candidate.candidate_type === 'novel_rule' ? candidate.rule_title : '本轮未生成全新规则',
      subtitle: candidate.candidate_type === 'novel_rule' ? displayMode(currentMode.value) : '未激活',
      body: candidate.candidate_type === 'novel_rule' ? candidate.rule_text : '当前结果仍然建立在旧规则之上，没有进入全新规则生成路径。',
      points: candidate.candidate_type === 'novel_rule' ? [
        `知识来源: ${(candidate.knowledge_sources || []).map(displayKnowledgeSource).join(' / ') || '暂无'}`,
        `依据度: ${formatScore(candidate.grounding_score)}`,
        `涌现度: ${formatScore(candidate.speculation_score)}`
      ] : [
        `审查关系: ${relationLine}`,
        `开放问题: ${(resultData.value?.open_questions || []).join('；') || '无'}`
      ],
      chips: candidate.candidate_type === 'novel_rule' ? (candidate.knowledge_sources || []) : [],
      tone: 'wine'
    }
  ]
})

function stateForStage(stage, currentStage) {
  const index = stageOrder.indexOf(stage)
  const currentIndex = stageOrder.indexOf(currentStage)
  if (resultData.value && stage === 'decision') return 'done'
  if (currentIndex === -1) return 'idle'
  if (index < currentIndex) return 'done'
  if (index === currentIndex) return 'active'
  return 'idle'
}

function stageMeta(stage) {
  const payload = stagePayloads[stage]
  if (!payload) return '待处理'
  if (stage === 'analogies') return `${(payload.reuse_candidates || []).length + (payload.adaptation_candidates || []).length} 条规则引用`
  if (stage === 'evidence') return `${(payload.evidence_items || []).length} 条证据`
  if (stage === 'candidates') return `${(payload.candidates || []).length} 条候选规则`
  if (stage === 'validation') return `${(payload.candidates || []).length} 条已审查`
  return '就绪'
}

function timestampForStage(stage) {
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
    novel_rule: '生成全新规则',
    insufficient_evidence: '证据不足'
  }[value] || value || '--'
}

function displayValidationStatus(value) {
  return {
    provisionally_supported: '初步支持',
    weakly_supported: '支持较弱',
    supported: '支持',
    rejected: '驳回'
  }[value] || value || '--'
}

function displayCandidateType(value) {
  return {
    adapted_rule: '改造规则',
    exact_reuse: '直接复用',
    novel_rule: '全新规则'
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

function addRule() {
  form.rules.push(defaultRule())
}

function removeRule(index) {
  form.rules.splice(index, 1)
}

function addDocument() {
  form.documents.push(defaultDocument())
}

function removeDocument(index) {
  form.documents.splice(index, 1)
}

function loadDemoPreset(mode) {
  const preset = mode === 'emergent' ? createEmergentPreset() : createGroundedPreset()
  Object.assign(form, preset)
}

function resetRuntimeState() {
  stopPolling()
  activeTaskId.value = ''
  taskData.value = null
  resultData.value = null
  logs.value = []
  stageNames.value = []
  logCursor.value = 0
  clearRevealTimers()
  revealedCardKeys.value = []
  for (const key of Object.keys(stagePayloads)) {
    delete stagePayloads[key]
  }
}

async function startDiscovery() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  resetRuntimeState()

  try {
    const preparedRules = form.rules
      .filter(rule => rule.title.trim() && rule.content.trim())
      .map((rule, index) => ({
        rule_id: `R-${String(index + 1).padStart(3, '0')}`,
        title: rule.title.trim(),
        content: rule.content.trim(),
        conditions: splitList(rule.conditionsText),
        source: rule.source.trim()
      }))
    submittedRules.value = preparedRules

    const ruleSetPayload = {
      name: `discovery-rules-${Date.now()}`,
      rules: preparedRules
    }
    const ruleSetRes = await importRuleSet(ruleSetPayload)

    const documentSetPayload = {
      name: `discovery-docs-${Date.now()}`,
      documents: form.documents
        .filter(doc => doc.title.trim() && doc.content.trim())
        .map(doc => ({
          title: doc.title.trim(),
          content: doc.content.trim()
        }))
    }
    const documentSetRes = await importDocuments(documentSetPayload)

    const taskRes = await createDiscoveryTask({
      query: form.query.trim(),
      context: form.context.trim(),
      rule_set_id: ruleSetRes.data.rule_set_id,
      document_set_id: documentSetRes.data.document_set.document_set_id,
      use_llm: form.useLlm,
      discovery_mode: form.discoveryMode,
      deduplicate: form.deduplicate,
      metadata: {
        timeout_seconds: form.timeoutSeconds
      }
    })

    activeTaskId.value = taskRes.data.task_id
    taskData.value = taskRes.data
    startPolling()
  } catch (error) {
    console.error('启动 discovery 失败:', error)
  } finally {
    submitting.value = false
  }
}

async function rerunTask() {
  if (!activeTaskId.value) return
  try {
    const res = await rerunDiscoveryTask(activeTaskId.value, {
      use_llm: form.useLlm,
      discovery_mode: form.discoveryMode,
      metadata: {
        timeout_seconds: form.timeoutSeconds
      }
    })
    resetRuntimeState()
    activeTaskId.value = res.data.task_id
    taskData.value = res.data
    startPolling()
  } catch (error) {
    console.error('重跑任务失败:', error)
  }
}

async function cancelTaskRun() {
  if (!activeTaskId.value) return
  try {
    await cancelDiscoveryTask(activeTaskId.value)
  } catch (error) {
    console.error('取消任务失败:', error)
  }
}

function openReport() {
  if (!activeTaskId.value) return
  router.push({ name: 'DiscoveryReport', params: { taskId: activeTaskId.value } })
}

async function refreshTask() {
  if (!activeTaskId.value) return
  const [taskRes, logsRes, stagesRes] = await Promise.all([
    getDiscoveryTask(activeTaskId.value),
    getDiscoveryLogs(activeTaskId.value, 0),
    getDiscoveryStages(activeTaskId.value)
  ])

  taskData.value = taskRes.data
  logs.value = logsRes.data.logs || []
  stageNames.value = stagesRes.data.stages || []

  for (const stage of stageNames.value) {
    if (!stagePayloads[stage] || ['problem_frame', 'analogies', 'evidence', 'candidates', 'validation'].includes(stage)) {
      const stageRes = await getDiscoveryStage(activeTaskId.value, stage)
      stagePayloads[stage] = stageRes.data.payload
    }
  }

  if (['completed', 'need_human_review', 'insufficient_evidence'].includes(taskData.value.status)) {
    const resultRes = await getDiscoveryResult(activeTaskId.value)
    resultData.value = resultRes.data
    stopPolling()
  }

  if (['failed', 'timed_out', 'cancelled'].includes(taskData.value.status)) {
    stopPolling()
  }
}

function startPolling() {
  stopPolling()
  refreshTask()
  pollHandle.value = window.setInterval(() => {
    refreshTask().catch(error => {
      console.error('轮询 discovery 失败:', error)
      stopPolling()
    })
  }, 1800)
}

function stopPolling() {
  if (pollHandle.value) {
    clearInterval(pollHandle.value)
    pollHandle.value = null
  }
}

function clearRevealTimers() {
  for (const timer of revealTimers.value) {
    clearTimeout(timer)
  }
  revealTimers.value = []
}

function scrollDiscussionToLatest(behavior = 'smooth') {
  const element = discussionFeedRef.value
  if (!element) return
  element.scrollTo({
    top: element.scrollHeight,
    behavior
  })
}

function splitList(text) {
  return (text || '')
    .split(/[\/；;,，]/)
    .map(item => item.trim())
    .filter(Boolean)
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

const canRerun = computed(() => !!activeTaskId.value && !submitting.value)
const canCancel = computed(() => {
  const status = taskData.value?.status
  return !!activeTaskId.value && !['completed', 'failed', 'need_human_review', 'insufficient_evidence', 'timed_out', 'cancelled'].includes(status)
})

watch(
  discussionCards,
  (cards) => {
    const known = new Set(revealedCardKeys.value)
    const missing = cards.filter(card => !known.has(card.key))
    if (!missing.length) return

    missing.forEach((card, index) => {
      const timer = window.setTimeout(() => {
        revealedCardKeys.value = [...revealedCardKeys.value, card.key]
      }, index * 220)
      revealTimers.value.push(timer)
    })
  },
  { deep: true }
)

watch(
  () => visibleDiscussionCards.value.length,
  async (newLength, oldLength) => {
    if (newLength <= oldLength) return
    await nextTick()
    scrollDiscussionToLatest(newLength - oldLength > 1 ? 'auto' : 'smooth')
  }
)

onBeforeUnmount(() => {
  stopPolling()
  clearRevealTimers()
})

onMounted(() => {
  const taskId = String(route.query.taskId || '').trim()
  if (!taskId) return
  activeTaskId.value = taskId
  refreshTask().catch(error => {
    console.error('载入指定 discovery 任务失败:', error)
  })
  startPolling()
})
</script>

<style scoped>
:root {
  --ink: #0d1317;
  --paper: #f6f2e8;
  --ash: #dcd1bb;
  --muted: #6d655a;
  --accent: #c2461b;
  --teal: #1d6f74;
  --olive: #6a7e3b;
  --wine: #6e2d39;
}

.discovery-workbench {
  min-height: 100vh;
  background:
    radial-gradient(circle at top right, rgba(194, 70, 27, 0.08), transparent 28%),
    radial-gradient(circle at bottom left, rgba(29, 111, 116, 0.12), transparent 32%),
    var(--paper);
  color: var(--ink);
  font-family: 'Space Grotesk', 'Noto Sans SC', sans-serif;
}

.discovery-workbench.embed-mode {
  min-height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  padding: 28px 34px 18px;
  border-bottom: 1px solid rgba(13, 19, 23, 0.12);
  background: rgba(246, 242, 232, 0.88);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.header-left {
  flex: 1;
  min-width: 0;
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  letter-spacing: 0.18em;
  font-weight: 800;
  cursor: pointer;
  margin-bottom: 18px;
}

.mode-strip {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.mode-pill {
  border: 1px solid rgba(13, 19, 23, 0.16);
  background: rgba(255, 255, 255, 0.55);
  border-radius: 18px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 210px;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.mode-pill:hover {
  transform: translateY(-2px);
}

.mode-pill.active {
  border-color: rgba(194, 70, 27, 0.55);
  background: rgba(194, 70, 27, 0.1);
}

.mode-name {
  font-weight: 700;
}

.mode-hint {
  color: var(--muted);
  font-size: 12px;
}

.header-right {
  display: flex;
  gap: 12px;
}

.header-stat {
  min-width: 120px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(13, 19, 23, 0.12);
}

.stat-label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
  margin-bottom: 8px;
}

.stat-value {
  font-size: 14px;
  font-weight: 700;
}

.mono {
  font-family: 'JetBrains Mono', monospace;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  text-transform: uppercase;
}

.status-active {
  background: rgba(29, 111, 116, 0.16);
  color: var(--teal);
}

.status-done {
  background: rgba(106, 126, 59, 0.18);
  color: var(--olive);
}

.status-error {
  background: rgba(110, 45, 57, 0.16);
  color: var(--wine);
}

.status-idle {
  background: rgba(13, 19, 23, 0.08);
  color: var(--muted);
}

.page-body {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 24px;
  padding: 24px;
}

.discovery-workbench.embed-mode .page-body {
  grid-template-columns: 1fr;
  gap: 0;
  padding: 0;
}

.control-panel,
.analysis-panel {
  min-width: 0;
}

.control-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel-card {
  border: 1px solid rgba(13, 19, 23, 0.12);
  background: rgba(255, 255, 255, 0.65);
  border-radius: 24px;
  padding: 20px;
  box-shadow: 0 18px 35px rgba(13, 19, 23, 0.06);
}

.intro-card {
  background:
    linear-gradient(140deg, rgba(13, 19, 23, 0.96), rgba(13, 19, 23, 0.84)),
    rgba(13, 19, 23, 0.94);
  color: #fffaf1;
}

.card-topline,
.panel-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: rgba(255, 255, 255, 0.66);
}

.card-title {
  font-size: 28px;
  line-height: 1.1;
  margin: 14px 0 12px;
}

.card-desc {
  font-size: 14px;
  line-height: 1.7;
  color: rgba(255, 250, 241, 0.82);
}

.intro-actions,
.cta-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.hero-cta-row {
  margin-top: 18px;
}

.ghost-btn,
.secondary-btn,
.add-row-btn,
.primary-btn,
.hero-run-btn {
  border: none;
  border-radius: 999px;
  padding: 11px 16px;
  cursor: pointer;
  font-weight: 700;
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.ghost-btn:hover,
.secondary-btn:hover,
.add-row-btn:hover,
.primary-btn:hover,
.hero-run-btn:hover {
  transform: translateY(-1px);
}

.ghost-btn {
  background: rgba(255, 250, 241, 0.1);
  color: #fffaf1;
}

.primary-btn {
  background: var(--accent);
  color: white;
  min-width: 170px;
}

.hero-run-btn {
  width: 100%;
  min-height: 56px;
  font-size: 16px;
  letter-spacing: 0.04em;
  background: linear-gradient(135deg, var(--accent), #da6e25);
  color: white;
  box-shadow: 0 16px 28px rgba(194, 70, 27, 0.22);
}

.secondary-btn {
  background: rgba(13, 19, 23, 0.08);
  color: var(--ink);
}

.secondary-btn.danger {
  background: rgba(110, 45, 57, 0.12);
  color: var(--wine);
}

.primary-btn:disabled,
.secondary-btn:disabled,
.hero-run-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}

.section-head {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}

.section-index {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--muted);
}

.section-title {
  font-weight: 700;
}

.rule-list,
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rule-editor,
.doc-editor,
.candidate-card {
  border: 1px solid rgba(13, 19, 23, 0.1);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.72);
}

.rule-editor-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.rule-badge {
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--muted);
}

.mini-remove {
  border: none;
  background: transparent;
  color: var(--wine);
  cursor: pointer;
  font-size: 12px;
}

.text-input,
.text-area {
  width: 100%;
  border: 1px solid rgba(13, 19, 23, 0.12);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.92);
  font-family: inherit;
  font-size: 14px;
  margin-bottom: 10px;
  resize: vertical;
}

.text-area.compact {
  min-height: 92px;
}

.inline-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.add-row-btn {
  background: rgba(13, 19, 23, 0.07);
  color: var(--ink);
  width: 100%;
}

.option-grid {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.toggle-box {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
}

.slider-box {
  width: 100%;
  border: 1px solid rgba(13, 19, 23, 0.12);
  border-radius: 14px;
  padding: 12px 14px;
}

.slider-label {
  font-size: 12px;
  color: var(--muted);
  display: block;
  margin-bottom: 8px;
}

.slider-box input[type="range"] {
  width: 100%;
}

.slider-value {
  display: block;
  margin-top: 8px;
  font-size: 12px;
}

.result-card .result-tag {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(13, 19, 23, 0.08);
  font-size: 11px;
  text-transform: uppercase;
  margin-right: 8px;
}

.result-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.result-tag--accent {
  background: rgba(194, 70, 27, 0.12);
  color: var(--accent);
}

.result-summary {
  margin: 14px 0 16px;
  line-height: 1.7;
}

.exploration-banner {
  margin: 0 0 16px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(194, 70, 27, 0.1);
  color: var(--accent);
  line-height: 1.65;
  font-size: 14px;
}

.candidate-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.candidate-title {
  font-weight: 800;
}

.candidate-meta {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}

.candidate-text {
  line-height: 1.7;
  margin-bottom: 12px;
}

.comparison-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
}

.comparison-card {
  position: relative;
  border: 1px solid rgba(13, 19, 23, 0.12);
  border-radius: 20px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.78);
  min-height: 220px;
  overflow: hidden;
}

.comparison-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 4px;
  background: rgba(13, 19, 23, 0.08);
}

.comparison-sand::before { background: rgba(90, 68, 44, 0.38); }
.comparison-teal::before { background: rgba(29, 111, 116, 0.45); }
.comparison-wine::before { background: rgba(110, 45, 57, 0.45); }

.comparison-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--muted);
  margin-bottom: 10px;
}

.comparison-title {
  font-size: 20px;
  font-weight: 800;
  line-height: 1.2;
}

.comparison-subtitle {
  color: var(--muted);
  font-size: 11px;
  margin-top: 6px;
}

.comparison-body {
  margin-top: 14px;
  line-height: 1.7;
}

.comparison-points {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
}

.comparison-point {
  font-size: 13px;
  line-height: 1.6;
  color: #27323a;
}

.comparison-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.comparison-chip {
  font-size: 11px;
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(13, 19, 23, 0.07);
}

.provenance-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.source-chip {
  font-size: 11px;
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(29, 111, 116, 0.12);
  color: var(--teal);
}

.score-cluster {
  display: flex;
  gap: 10px;
}

.score-item {
  min-width: 62px;
  text-align: right;
}

.score-label {
  display: block;
  font-size: 11px;
  color: var(--muted);
}

.score-value {
  font-size: 14px;
  font-weight: 700;
}

.open-questions {
  margin-top: 16px;
}

.rejected-block {
  margin-top: 18px;
}

.subheading {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--muted);
  margin-bottom: 8px;
}

.question-line {
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 0;
  border-top: 1px dashed rgba(13, 19, 23, 0.08);
}

.rejected-line {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 0;
  border-top: 1px dashed rgba(13, 19, 23, 0.08);
}

.rejected-id {
  font-size: 11px;
  color: var(--wine);
}

.rejected-reason {
  font-size: 13px;
  line-height: 1.6;
  color: #29343c;
}

.analysis-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.analysis-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px 300px;
  gap: 18px;
}

.workflow-band,
.metric-board,
.agent-radar,
.discussion-column,
.evidence-column {
  border: 1px solid rgba(13, 19, 23, 0.12);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 18px 35px rgba(13, 19, 23, 0.05);
}

.workflow-band {
  padding: 18px;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.workflow-node {
  border: 1px solid rgba(13, 19, 23, 0.08);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.74);
}

.node-active {
  border-color: rgba(194, 70, 27, 0.45);
  background: rgba(194, 70, 27, 0.08);
}

.node-done {
  border-color: rgba(106, 126, 59, 0.4);
  background: rgba(106, 126, 59, 0.1);
}

.node-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(13, 19, 23, 0.15);
  margin-bottom: 10px;
}

.node-active .node-dot {
  background: var(--accent);
}

.node-done .node-dot {
  background: var(--olive);
}

.node-index {
  font-size: 11px;
  color: var(--muted);
  margin-right: 8px;
}

.node-title {
  font-weight: 700;
}

.node-meta {
  margin-top: 8px;
  font-size: 11px;
  color: var(--muted);
}

.metric-board {
  padding: 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.agent-radar {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.radar-copy {
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted);
}

.agent-orbit {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px 10px;
}

.orbit-agent {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}

.orbit-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(13, 19, 23, 0.14);
  border: 1px solid rgba(13, 19, 23, 0.08);
  box-shadow: inset 0 0 0 4px rgba(255, 255, 255, 0.35);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, opacity 0.2s ease;
  opacity: 0.45;
}

.orbit-label {
  font-size: 10px;
  color: var(--muted);
  line-height: 1;
}

.orbit-seen .orbit-dot {
  opacity: 0.92;
}

.orbit-active .orbit-dot {
  transform: scale(1.18);
  opacity: 1;
  animation: orbitPulse 1.2s ease-in-out infinite;
}

.orbit-tone-blue .orbit-dot { background: rgba(40, 85, 166, 0.88); }
.orbit-tone-teal .orbit-dot { background: rgba(29, 111, 116, 0.88); }
.orbit-tone-orange .orbit-dot { background: rgba(198, 99, 24, 0.88); }
.orbit-tone-green .orbit-dot { background: rgba(60, 122, 64, 0.88); }
.orbit-tone-purple .orbit-dot { background: rgba(106, 59, 184, 0.88); }
.orbit-tone-red .orbit-dot { background: rgba(164, 50, 50, 0.88); }
.orbit-tone-wine .orbit-dot { background: rgba(110, 45, 57, 0.9); }
.orbit-tone-black .orbit-dot { background: rgba(16, 20, 24, 0.92); }

.metric-card {
  border-radius: 18px;
  padding: 14px;
  background: rgba(246, 242, 232, 0.86);
}

.metric-name {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 8px;
}

.metric-data {
  font-size: 18px;
  font-weight: 700;
}

.conversation-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(280px, 0.72fr);
  gap: 18px;
  min-height: 0;
}

.discussion-column,
.evidence-column {
  padding: 18px;
}

.panel-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-title-row--spaced {
  margin-top: 24px;
}

.panel-note {
  font-size: 11px;
  color: var(--muted);
}

.discussion-feed,
.ledger-list,
.log-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: calc(100vh - 250px);
  overflow: auto;
  padding-right: 4px;
}

.discussion-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.empty-state {
  border: 1px dashed rgba(13, 19, 23, 0.16);
  border-radius: 20px;
  padding: 24px;
  background: rgba(246, 242, 232, 0.72);
}

.empty-title {
  font-weight: 800;
  margin-bottom: 10px;
}

.empty-copy {
  line-height: 1.7;
  color: var(--muted);
}

.agent-card {
  border-radius: 22px;
  padding: 16px;
  border: 1px solid rgba(13, 19, 23, 0.1);
  background: rgba(255, 255, 255, 0.82);
  transform-origin: top left;
}

.agent-live {
  box-shadow: 0 0 0 1px rgba(194, 70, 27, 0.14), 0 18px 30px rgba(194, 70, 27, 0.08);
}

.agent-blue { border-left: 5px solid #2855a6; }
.agent-orange { border-left: 5px solid #c66318; }
.agent-green { border-left: 5px solid #3c7a40; }
.agent-purple { border-left: 5px solid #6a3bb8; }
.agent-red { border-left: 5px solid #a43232; }
.agent-black { border-left: 5px solid #101418; }

.agent-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(13, 19, 23, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
}

.agent-meta {
  flex: 1;
}

.agent-name {
  font-weight: 800;
}

.agent-stage {
  color: var(--muted);
  font-size: 11px;
}

.agent-time {
  color: var(--muted);
  font-size: 11px;
}

.agent-time-cluster {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.agent-live-indicator {
  display: inline-flex;
  gap: 4px;
}

.agent-live-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulseDot 1s ease-in-out infinite;
}

.agent-live-indicator span:nth-child(2) { animation-delay: 0.16s; }
.agent-live-indicator span:nth-child(3) { animation-delay: 0.32s; }

.agent-headline {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 10px;
}

.agent-points {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.point-line {
  line-height: 1.65;
  color: #1b2329;
  opacity: 0;
  transform: translateY(6px);
  animation: pointReveal 0.42s ease forwards;
  animation-delay: var(--point-delay, 0ms);
}

.agent-raw {
  margin-top: 12px;
}

.agent-raw summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--muted);
}

.agent-raw pre {
  margin-top: 8px;
  padding: 12px;
  border-radius: 14px;
  background: #0f1417;
  color: #eff3ec;
  overflow: auto;
  font-size: 12px;
  line-height: 1.55;
}

.ledger-item,
.log-line {
  border: 1px solid rgba(13, 19, 23, 0.08);
  border-radius: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.74);
}

.ledger-head,
.log-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.ledger-stage,
.log-stage {
  font-weight: 700;
}

.ledger-duration,
.ledger-time,
.log-time {
  color: var(--muted);
  font-size: 11px;
}

.log-message {
  line-height: 1.6;
  color: #233039;
}

.card-flow-enter-active,
.card-flow-leave-active {
  transition: opacity 0.32s ease, transform 0.32s ease;
}

.card-flow-enter-from,
.card-flow-leave-to {
  opacity: 0;
  transform: translateY(18px) scale(0.98);
}

@keyframes pulseDot {
  0%, 100% { opacity: 0.32; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}

@keyframes orbitPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(194, 70, 27, 0.18); }
  50% { box-shadow: 0 0 0 8px rgba(194, 70, 27, 0.04); }
}

@keyframes pointReveal {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1280px) {
  .page-body {
    grid-template-columns: 1fr;
  }

  .analysis-top,
  .conversation-layout,
  .inline-grid,
  .comparison-board {
    grid-template-columns: 1fr;
  }

  .workflow-band {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-orbit {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .page-header {
    padding: 20px;
    flex-direction: column;
  }

  .page-body {
    padding: 16px;
  }

  .workflow-band {
    grid-template-columns: 1fr;
  }
}
</style>
