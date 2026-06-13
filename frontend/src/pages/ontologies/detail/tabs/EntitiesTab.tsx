import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ontologyApi } from '@/api/ontologies'
import ConfidenceBar from '@/components/ConfidenceBar'
import ConfirmDialog from '@/components/ConfirmDialog'
import { Pencil, Trash2, Plus, Search } from 'lucide-react'
import type { Entity } from '@/types/ontology'

export default function EntitiesTab({ ontologyId }: { ontologyId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Entity | null>(null)
  const { register, handleSubmit, reset } = useForm<Partial<Entity>>()

  const { data: entities = [], isLoading } = useQuery({
    queryKey: ['entities', ontologyId],
    queryFn: () => ontologyApi.listEntities(ontologyId) as any,
  })

  const createMut = useMutation({
    mutationFn: (data: Partial<Entity>) => ontologyApi.createEntity(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities', ontologyId] }); qc.invalidateQueries({ queryKey: ['stats'] }); setShowCreate(false); reset() },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteEntity(ontologyId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities', ontologyId] }); qc.invalidateQueries({ queryKey: ['stats'] }) },
  })

  const allTypes = useMemo(() => {
    const s = new Set<string>()
    ;(entities as Entity[]).forEach(e => { if (e.type) s.add(e.type) })
    return Array.from(s).sort()
  }, [entities])

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return (entities as Entity[]).filter(e => {
      const matchQ = !q || e.name_cn?.toLowerCase().includes(q) || e.name_en?.toLowerCase().includes(q) || e.type?.toLowerCase().includes(q)
      const matchType = !typeFilter || e.type === typeFilter
      return matchQ && matchType
    })
  }, [entities, searchQ, typeFilter])

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
            placeholder="搜索名称 / 类型…"
            className="w-full border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black" />
        </div>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm text-gray-600">
          <option value="">全部类型</option>
          {allTypes.map(tp => <option key={tp} value={tp}>{tp}</option>)}
        </select>
      </div>
      <div className="flex justify-end">
        <button onClick={() => { setShowCreate(true); reset() }}
          className="flex items-center gap-2 px-3 py-2 bg-black text-white rounded-lg text-sm">
          <Plus size={14} /> {t('entities.add')}
        </button>
      </div>

      <div className="bg-white border rounded-lg overflow-hidden">
        {isLoading ? <p className="py-8 text-center text-gray-400">{t('common.loading')}</p> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>{[t('entities.col_name_cn'), t('entities.col_name_en'), t('entities.col_type'), t('entities.col_desc'), t('entities.col_confidence'), t('entities.col_actions')].map(h => (
                <th key={h} className="px-4 py-3 text-left text-gray-500 text-xs font-medium">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {filtered.map(e => (
                <tr key={e.id} className="border-b hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)}>
                  <td className="px-4 py-3 font-medium">{e.name_cn}</td>
                  <td className="px-4 py-3 text-gray-500">{e.name_en || '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{e.type || '—'}</td>
                  <td className="px-4 py-3 text-gray-500 max-w-xs truncate">{e.description || '—'}</td>
                  <td className="px-4 py-3 w-32"><ConfidenceBar value={e.confidence} /></td>
                  <td className="px-4 py-3" onClick={ev => ev.stopPropagation()}>
                    <div className="flex items-center gap-3">
                      <button onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)} title={t('common.edit')} className="p-1.5 rounded text-blue-500 hover:bg-blue-50"><Pencil size={14} /></button>
                      <button onClick={() => setDeleteTarget(e)} title={t('common.delete')} className="p-1.5 rounded text-red-500 hover:bg-red-50"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!isLoading && filtered.length === 0 && (
          <p className="text-center text-gray-400 py-8">{searchQ || typeFilter ? '无匹配结果' : t('entities.empty')}</p>
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg p-6 w-96">
            <h3 className="font-semibold mb-4">{t('entities.add')}</h3>
            <form onSubmit={handleSubmit(data => createMut.mutate(data))} className="space-y-3">
              <input {...register('name_cn', { required: true })} placeholder={t('entities.ph_name_cn')} className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input {...register('name_en')} placeholder={t('entities.ph_name_en')} className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input {...register('type')} placeholder={t('entities.ph_type')} className="w-full border rounded-lg px-3 py-2 text-sm" />
              <textarea {...register('description')} placeholder={t('entities.ph_desc')} rows={2} className="w-full border rounded-lg px-3 py-2 text-sm resize-none" />
              <input {...register('confidence', { valueAsNumber: true })} type="number" step="0.01" min="0" max="1" placeholder={t('entities.ph_confidence')} className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => { setShowCreate(false); reset() }} className="px-4 py-2 border rounded-lg text-sm">{t('common.cancel')}</button>
                <button type="submit" className="px-4 py-2 bg-black text-white rounded-lg text-sm">{t('common.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('entities.delete_title')}
        message={t('entities.delete_confirm', { name: deleteTarget?.name_cn ?? '' })}
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget.id); setDeleteTarget(null) }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
