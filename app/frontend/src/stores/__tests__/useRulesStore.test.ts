import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRulesStore } from '../useRulesStore'
import type { ForwardRule } from '@/types/rule'

describe('useRulesStore', () => {
  beforeEach(() => {
    // 重置store
    const { result } = renderHook(() => useRulesStore())
    act(() => {
      result.current.setRules([])
      result.current.setSearchText('')
      result.current.clearFilters()
    })
  })

  it('should set rules', () => {
    const { result } = renderHook(() => useRulesStore())

    const mockRules: ForwardRule[] = [
      {
        id: 1,
        name: 'Test Rule',
        source_chat_id: '123',
        delivery_mode: 'auto',
        destination_ids: [],
        delivery_targets: [],
        is_active: true,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
      } as unknown as ForwardRule,
    ]

    act(() => {
      result.current.setRules(mockRules)
    })

    expect(result.current.rules).toEqual(mockRules)
  })

  it('should toggle rule selection', () => {
    const { result } = renderHook(() => useRulesStore())

    act(() => {
      result.current.toggleSelectedRule(1)
    })

    expect(result.current.selectedRuleIds).toContain(1)

    act(() => {
      result.current.toggleSelectedRule(1)
    })

    expect(result.current.selectedRuleIds).not.toContain(1)
  })

  it('should filter rules by search text', () => {
    const { result } = renderHook(() => useRulesStore())

    const mockRules: ForwardRule[] = [
      {
        id: 1,
        name: 'Test Rule 1',
        source_chat_id: '123',
        delivery_mode: 'auto',
        destination_ids: [],
        delivery_targets: [],
        is_active: true,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
      } as unknown as ForwardRule,
      {
        id: 2,
        name: 'Another Rule',
        source_chat_id: '789',
        delivery_mode: 'manual',
        destination_ids: [],
        delivery_targets: [],
        is_active: false,
        created_at: '2025-01-02',
        updated_at: '2025-01-02',
      } as unknown as ForwardRule,
    ]

    act(() => {
      result.current.setRules(mockRules)
      result.current.setSearchText('test')
    })

    const filtered = result.current.getFilteredRules()
    expect(filtered).toHaveLength(1)
    expect(filtered[0].name).toBe('Test Rule 1')
  })

  it('should calculate stats correctly', () => {
    const { result } = renderHook(() => useRulesStore())

    const mockRules: ForwardRule[] = [
      {
        id: 1,
        name: 'Active Rule',
        is_active: true,
        enable_keyword_filter: true,
        enable_regex_replace: false,
      } as ForwardRule,
      {
        id: 2,
        name: 'Inactive Rule',
        is_active: false,
        enable_keyword_filter: false,
        enable_regex_replace: true,
      } as ForwardRule,
    ]

    act(() => {
      result.current.setRules(mockRules)
    })

    const stats = result.current.getStats()
    expect(stats.total).toBe(2)
    expect(stats.active).toBe(1)
    expect(stats.inactive).toBe(1)
    expect(stats.withKeywords).toBe(1)
    expect(stats.withReplacements).toBe(1)
  })
})
