'use client'

import { useState, useCallback } from 'react'
import type { CommunityComment, CommunityCommentResponse } from '@/lib/types'

// ─── Time Formatting ────────────────────────────────────────

function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then

  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`

  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

// ─── Comment Form ───────────────────────────────────────────

interface CommentFormProps {
  agendaItemId: string
  parentCommentId?: string
  onSubmitted: (comment: CommunityComment) => void
  onCancel?: () => void
  placeholder?: string
  compact?: boolean
}

function CommentForm({
  agendaItemId,
  parentCommentId,
  onSubmitted,
  onCancel,
  placeholder = 'Share your thoughts on this item...',
  compact = false,
}: CommentFormProps) {
  const [authorName, setAuthorName] = useState('')
  const [authorEmail, setAuthorEmail] = useState('')
  const [commentText, setCommentText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = useCallback(async () => {
    setError(null)
    setSubmitting(true)

    try {
      const res = await fetch('/api/community-comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agenda_item_id: agendaItemId,
          parent_comment_id: parentCommentId,
          author_name: authorName.trim(),
          author_email: authorEmail.trim() || undefined,
          comment_text: commentText.trim(),
        }),
      })

      const data: CommunityCommentResponse = await res.json()

      if (!data.success) {
        setError(data.error ?? 'Failed to submit comment.')
        return
      }

      // Build optimistic comment for immediate display
      const newComment: CommunityComment = {
        id: data.comment_id!,
        city_fips: '0660620',
        agenda_item_id: agendaItemId,
        parent_comment_id: parentCommentId ?? null,
        author_name: authorName.trim(),
        comment_text: commentText.trim(),
        status: 'published',
        submitted_to_clerk: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        replies: [],
      }

      onSubmitted(newComment)
      setCommentText('')
      if (!parentCommentId) {
        // Keep name/email for top-level follow-up comments
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }, [agendaItemId, parentCommentId, authorName, authorEmail, commentText, onSubmitted])

  const canSubmit = authorName.trim().length >= 2 && commentText.trim().length >= 5 && !submitting

  return (
    <div className={compact ? 'ml-8 mt-2' : ''}>
      {!compact && (
        <div className="flex gap-3 mb-3">
          <div className="flex-1">
            <label htmlFor="author-name" className="block text-xs font-medium text-slate-600 mb-1">
              Your name <span className="text-red-400">*</span>
            </label>
            <input
              id="author-name"
              type="text"
              value={authorName}
              onChange={(e) => setAuthorName(e.target.value)}
              placeholder="Full name"
              maxLength={200}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
            />
          </div>
          <div className="flex-1">
            <label htmlFor="author-email" className="block text-xs font-medium text-slate-600 mb-1">
              Email <span className="text-slate-400">(optional)</span>
            </label>
            <input
              id="author-email"
              type="email"
              value={authorEmail}
              onChange={(e) => setAuthorEmail(e.target.value)}
              placeholder="For clerk submission records"
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
            />
          </div>
        </div>
      )}

      <textarea
        value={commentText}
        onChange={(e) => setCommentText(e.target.value)}
        placeholder={placeholder}
        maxLength={5000}
        rows={compact ? 2 : 3}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy resize-y"
      />

      {error && (
        <p className="text-xs text-red-600 mt-1" role="alert">{error}</p>
      )}

      <div className="flex items-center gap-2 mt-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="px-4 py-1.5 text-sm font-medium text-white bg-civic-navy rounded-md hover:bg-civic-navy-light disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Submitting...' : compact ? 'Reply' : 'Comment'}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
          >
            Cancel
          </button>
        )}
        <span className="text-xs text-slate-400 ml-auto">
          {commentText.length}/5,000
        </span>
      </div>
    </div>
  )
}

// ─── Single Comment ─────────────────────────────────────────

interface CommentCardProps {
  comment: CommunityComment
  agendaItemId: string
  onReplySubmitted: (parentId: string, reply: CommunityComment) => void
}

function CommentCard({ comment, agendaItemId, onReplySubmitted }: CommentCardProps) {
  const [showReplyForm, setShowReplyForm] = useState(false)

  return (
    <div className="py-3">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-sm font-medium text-slate-800">{comment.author_name}</span>
        <span className="text-xs text-slate-400">{timeAgo(comment.created_at)}</span>
        {comment.submitted_to_clerk && (
          <span className="text-[10px] font-medium text-green-700 bg-green-50 px-1.5 py-0.5 rounded">
            Submitted to Clerk
          </span>
        )}
      </div>

      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
        {comment.comment_text}
      </p>

      <button
        type="button"
        onClick={() => setShowReplyForm(!showReplyForm)}
        className="text-xs text-civic-navy-light hover:text-civic-navy mt-1 transition-colors"
      >
        {showReplyForm ? 'Cancel reply' : 'Reply'}
      </button>

      {showReplyForm && (
        <CommentForm
          agendaItemId={agendaItemId}
          parentCommentId={comment.id}
          compact
          placeholder={`Reply to ${comment.author_name}...`}
          onSubmitted={(reply) => {
            onReplySubmitted(comment.id, reply)
            setShowReplyForm(false)
          }}
          onCancel={() => setShowReplyForm(false)}
        />
      )}

      {/* Replies */}
      {comment.replies && comment.replies.length > 0 && (
        <div className="ml-6 border-l-2 border-slate-100 pl-4 mt-2">
          {comment.replies.map((reply) => (
            <div key={reply.id} className="py-2">
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-sm font-medium text-slate-800">{reply.author_name}</span>
                <span className="text-xs text-slate-400">{timeAgo(reply.created_at)}</span>
              </div>
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                {reply.comment_text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Main Section ───────────────────────────────────────────

interface CommunityCommentSectionProps {
  agendaItemId: string
  initialComments: CommunityComment[]
  meetingDate: string
  commentDeadline?: string | null
}

export default function CommunityCommentSection({
  agendaItemId,
  initialComments,
  meetingDate,
  commentDeadline,
}: CommunityCommentSectionProps) {
  const [comments, setComments] = useState<CommunityComment[]>(initialComments)

  // Comment window: open if meeting date is in the future
  const meetingDateObj = new Date(meetingDate + 'T00:00:00')
  const now = new Date()
  const isOpen = meetingDateObj > now

  // Deadline display: 24 hours before meeting date unless specified
  const deadlineDate = commentDeadline
    ? new Date(commentDeadline)
    : new Date(meetingDateObj.getTime() - 24 * 60 * 60 * 1000)
  const deadlinePassed = deadlineDate <= now

  const handleNewComment = useCallback((comment: CommunityComment) => {
    setComments((prev) => [...prev, comment])
  }, [])

  const handleReply = useCallback((parentId: string, reply: CommunityComment) => {
    setComments((prev) =>
      prev.map((c) =>
        c.id === parentId
          ? { ...c, replies: [...(c.replies ?? []), reply] }
          : c,
      ),
    )
  }, [])

  const totalCount = comments.reduce(
    (sum, c) => sum + 1 + (c.replies?.length ?? 0),
    0,
  )

  return (
    <section>
      <h2 className="text-lg font-semibold text-civic-navy mb-1">
        Community Discussion
      </h2>

      <p className="text-xs text-slate-500 mb-4">
        {isOpen ? (
          <>
            Comments {deadlinePassed ? 'were' : 'will be'} submitted to the City Clerk as part of the public record.
            {!deadlinePassed && (
              <> Deadline: <span className="font-medium text-slate-700">{deadlineDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</span></>
            )}
          </>
        ) : (
          <>
            This discussion was submitted to the City Clerk as part of the public record.
          </>
        )}
      </p>

      {/* Comment count */}
      {totalCount > 0 && (
        <p className="text-sm text-slate-600 mb-3">
          {totalCount} community {totalCount === 1 ? 'comment' : 'comments'}
        </p>
      )}

      {/* Existing comments */}
      {comments.length > 0 && (
        <div className="divide-y divide-slate-100 mb-4">
          {comments.map((comment) => (
            <CommentCard
              key={comment.id}
              comment={comment}
              agendaItemId={agendaItemId}
              onReplySubmitted={handleReply}
            />
          ))}
        </div>
      )}

      {/* New comment form */}
      {isOpen && !deadlinePassed ? (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
          <CommentForm
            agendaItemId={agendaItemId}
            onSubmitted={handleNewComment}
          />
        </div>
      ) : isOpen && deadlinePassed ? (
        <p className="text-sm text-slate-500 italic">
          The comment deadline for this meeting has passed.
        </p>
      ) : null}

      {/* Disclosure */}
      <p className="text-[10px] text-slate-400 mt-3">
        Comments are submitted to the Richmond City Clerk before the meeting. By commenting, you agree to have your name and comment included in the public record.
      </p>
    </section>
  )
}
