export type Phase = 'idle' | 'listening' | 'translating' | 'thinking' | 'speaking' | 'waiting' | 'muted'

declare module 'claude-code' {
  interface PluginState {
    mya: { phase: Phase; frame: number }
  }
}
