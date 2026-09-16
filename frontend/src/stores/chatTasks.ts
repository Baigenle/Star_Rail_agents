import { defineStore } from 'pinia'

import {
  createChatJob,
  getChatJob,
  getChatJobs,
  retryChatJob,
  sendMessage,
  streamChatJobEvents,
} from '../services/api'
import type { AIResponse, ChatJob, ChatJobEvent } from '../types/ai'

export interface AppNotification {
  id: string
  kind: 'success' | 'error'
  title: string
  message: string
  conversationId?: string
  jobId?: string
}

const NOTIFIED_KEY = 'star_rail_notified_chat_jobs'
const streamControllers = new Map<string, AbortController>()

export const useChatTaskStore = defineStore('chat-tasks', {
  state: () => ({
    jobs: {} as Record<string, ChatJob>,
    events: {} as Record<string, ChatJobEvent[]>,
    partialAnswers: {} as Record<string, string>,
    notifications: [] as AppNotification[],
    lastCompletedJobId: '',
    polling: false,
  }),
  getters: {
    activeJobs: (state) =>
      Object.values(state.jobs).filter((job) =>
        job.status === 'queued' || job.status === 'running'),
  },
  actions: {
    notifiedIds(): Set<string> {
      return new Set(JSON.parse(sessionStorage.getItem(NOTIFIED_KEY) ?? '[]'))
    },
    markNotified(id: string) {
      const ids = this.notifiedIds()
      ids.add(id)
      sessionStorage.setItem(NOTIFIED_KEY, JSON.stringify([...ids].slice(-100)))
    },
    notifyForJob(job: ChatJob) {
      if (this.notifiedIds().has(job.id)) return
      this.markNotified(job.id)
      if (job.status === 'completed') {
        this.lastCompletedJobId = job.id
        this.pushNotification({
          id: `chat-${job.id}`,
          kind: 'success',
          title: '黑塔已经完成回答',
          message: job.message,
          conversationId: job.conversation_id,
          jobId: job.id,
        })
      } else if (job.status === 'failed') {
        this.pushNotification({
          id: `chat-${job.id}`,
          kind: 'error',
          title: '这次问答没有完成',
          message: job.error_message || '可以稍后重试。',
          conversationId: job.conversation_id,
          jobId: job.id,
        })
      }
    },
    pushNotification(notification: AppNotification) {
      if (this.notifications.some((item) => item.id === notification.id)) return
      this.notifications.push(notification)
      if (notification.kind === 'success') {
        window.setTimeout(() => this.dismissNotification(notification.id), 8000)
      }
    },
    dismissNotification(id: string) {
      this.notifications = this.notifications.filter((item) => item.id !== id)
    },
    async initialize(isAuthenticated: boolean) {
      if (!isAuthenticated) return
      for (let attempt = 0; attempt < 5; attempt += 1) {
        const jobs = await getChatJobs()
        for (const job of jobs) {
          this.jobs[job.id] = job
          const age = Date.now() - new Date(job.created_at).getTime()
          if (age < 120_000 && (job.status === 'completed' || job.status === 'failed')) {
            this.notifyForJob(job)
          }
        }
        if (this.activeJobs.length) {
          for (const job of this.activeJobs) void this.startStream(job.id)
          return
        }
        if (attempt < 4) {
          await new Promise((resolve) => window.setTimeout(resolve, 2000))
        }
      }
    },
    async submitLogged(
      message: string,
      conversationId: string,
      history: Array<{ role: 'user' | 'assistant'; content: string }>,
    ): Promise<ChatJob> {
      const job = await createChatJob(message, conversationId, history)
      this.jobs[job.id] = job
      this.events[job.id] = []
      this.partialAnswers[job.id] = job.partial_answer || ''
      void this.startStream(job.id)
      return job
    },
    async submitAnonymous(
      message: string,
      history: Array<{ role: 'user' | 'assistant'; content: string }>,
    ): Promise<AIResponse> {
      try {
        const response = await sendMessage(message, undefined, history)
        this.pushNotification({
          id: `anonymous-${response.response_id}`,
          kind: 'success',
          title: '黑塔已经完成回答',
          message,
        })
        return response
      } catch (error) {
        this.pushNotification({
          id: `anonymous-error-${Date.now()}`,
          kind: 'error',
          title: '这次问答没有完成',
          message: '请检查后端与检索服务。',
        })
        throw error
      }
    },
    async startPolling() {
      if (this.polling) return
      this.polling = true
      try {
        while (this.activeJobs.length) {
          const active = [...this.activeJobs]
          await Promise.all(active.map(async (current) => {
            const job = await getChatJob(current.id)
            this.jobs[job.id] = job
            if (job.status === 'completed' || job.status === 'failed') {
              this.notifyForJob(job)
            }
          }))
          if (this.activeJobs.length) {
            await new Promise((resolve) => window.setTimeout(resolve, 2000))
          }
        }
      } finally {
        this.polling = false
      }
    },
    async startStream(id: string) {
      if (streamControllers.has(id)) return
      const controller = new AbortController()
      streamControllers.set(id, controller)
      const existing = this.events[id] ?? []
      const lastSequence = existing.at(-1)?.sequence ?? 0
      try {
        await streamChatJobEvents(
          id,
          (event) => {
            const current = this.events[id] ?? []
            if (!current.some((item) => item.sequence === event.sequence)) {
              this.events[id] = [...current, event].sort(
                (left, right) => left.sequence - right.sequence,
              )
            }
            if (event.event_type === 'answer.delta' && event.payload.delta) {
              this.partialAnswers[id] =
                `${this.partialAnswers[id] ?? ''}${event.payload.delta}`
            }
          },
          controller.signal,
          lastSequence,
        )
        const job = await getChatJob(id)
        this.jobs[id] = job
        this.partialAnswers[id] = job.partial_answer || this.partialAnswers[id] || ''
        if (job.status === 'completed' || job.status === 'failed') this.notifyForJob(job)
      } catch (error) {
        if (!controller.signal.aborted) void this.startPolling()
      } finally {
        streamControllers.delete(id)
      }
    },
    async retry(id: string) {
      const job = await retryChatJob(id)
      this.jobs[id] = job
      this.events[id] = []
      this.partialAnswers[id] = ''
      const notified = this.notifiedIds()
      notified.delete(id)
      sessionStorage.setItem(NOTIFIED_KEY, JSON.stringify([...notified]))
      void this.startStream(id)
    },
  },
})
