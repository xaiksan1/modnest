export type Phase = 'idle' | 'listening' | 'translating' | 'thinking' | 'speaking' | 'muted'

declare module 'claude-code' {
  interface PluginState {
    igor: { phase: Phase; frame: number }
  }
}
