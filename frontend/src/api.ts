import type { ChatResponse, ConversationSummary, Message, User } from './types';

const API_BASE = '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<void> {
  const token = await request<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem('token', token.access_token);
}

export async function getMe(): Promise<User> {
  return request<User>('/api/auth/me');
}

export async function getConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>('/api/conversations');
}

export async function getMessages(conversationId: number): Promise<Message[]> {
  return request<Message[]>(`/api/conversations/${conversationId}/messages`);
}

export async function uploadFile(file: File): Promise<{ document_id: number; filename: string; chunks_indexed: number }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/upload', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function sendChat(message: string, conversationId?: number): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
  });
}
