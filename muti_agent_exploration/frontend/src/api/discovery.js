import service, { requestWithRetry } from './index'

export const importRuleSet = (data) => {
  return requestWithRetry(() => service.post('/api/discovery/rule-sets/import', data), 2, 500)
}

export const importDocuments = (data) => {
  return requestWithRetry(() => service.post('/api/discovery/documents/import', data), 2, 500)
}

export const createDiscoveryTask = (data) => {
  return requestWithRetry(() => service.post('/api/discovery/tasks/discover-rule', data), 2, 500)
}

export const getDiscoveryTask = (taskId) => {
  return service.get(`/api/discovery/tasks/${taskId}`)
}

export const getDiscoveryResult = (taskId) => {
  return service.get(`/api/discovery/tasks/${taskId}/result`)
}

export const getDiscoveryLogs = (taskId, fromLine = 0) => {
  return service.get(`/api/discovery/tasks/${taskId}/logs`, { params: { from_line: fromLine } })
}

export const getDiscoveryStages = (taskId) => {
  return service.get(`/api/discovery/tasks/${taskId}/stages`)
}

export const getDiscoveryStage = (taskId, stage) => {
  return service.get(`/api/discovery/tasks/${taskId}/stages/${stage}`)
}

export const rerunDiscoveryTask = (taskId, data = {}) => {
  return requestWithRetry(() => service.post(`/api/discovery/tasks/${taskId}/rerun`, data), 2, 500)
}

export const cancelDiscoveryTask = (taskId) => {
  return service.post(`/api/discovery/tasks/${taskId}/cancel`)
}
