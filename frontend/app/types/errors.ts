export interface AppFieldError {
  field: string
  label: string
  message: string
}

export interface AppErrorDetails {
  title: string
  message: string
  /** Human-readable cause shown to the user (fields + hint). */
  reason?: string
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
  /** Extra cause line for errors (field reasons, server hint, etc.). */
  reason?: string
  createdAt: string
  read: boolean
  href?: string
}
