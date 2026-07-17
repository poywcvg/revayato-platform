export interface AppFieldError {
  field: string
  label: string
  message: string
}

export interface AppErrorDetails {
  title: string
  message: string
  hint?: string
  code?: string
  status?: number
  fields: AppFieldError[]
}

export type AppNotificationType = 'success' | 'error' | 'warning' | 'info'

export interface AppNotification {
  id: string
  type: AppNotificationType
  title: string
  message: string
  createdAt: string
  read: boolean
  href?: string
}
