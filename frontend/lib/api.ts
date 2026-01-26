/**
 * API client for the CRM backend
 */

const API_BASE = '/api';

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean>;
}

class APIClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('auth_token', token);
    } else {
      localStorage.removeItem('auth_token');
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token');
    }
    return this.token;
  }

  private async fetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
    const { params, ...fetchOptions } = options;

    let url = `${API_BASE}${endpoint}`;
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      url += `?${searchParams.toString()}`;
    }

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const token = this.getToken();
    if (token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: 'include',
    });

    if (response.status === 401) {
      this.setToken(null);
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Auth
  async login(password: string) {
    const response = await this.fetch<{ token: string; expires_in_hours: number }>(
      '/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ password }),
      }
    );
    this.setToken(response.token);
    return response;
  }

  async logout() {
    await this.fetch('/auth/logout', { method: 'POST' });
    this.setToken(null);
  }

  async checkAuth() {
    return this.fetch<{ authenticated: boolean }>('/auth/status');
  }

  // People
  async listPeople(params: {
    page?: number;
    page_size?: number;
    search?: string;
    tracked_only?: boolean;
    sort_by?: string;
    sort_order?: string;
  } = {}) {
    return this.fetch<PeopleListResponse>('/people', { params });
  }

  async getPerson(id: string) {
    return this.fetch<Person>(`/people/${id}`);
  }

  async updatePerson(id: string, data: Partial<Person>) {
    return this.fetch<Person>(`/people/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async promotePerson(id: string) {
    return this.fetch(`/people/${id}/promote`, { method: 'POST' });
  }

  async addTag(personId: string, tag: string) {
    return this.fetch(`/people/${personId}/tags`, {
      method: 'POST',
      params: { tag },
    });
  }

  async removeTag(personId: string, tag: string) {
    return this.fetch(`/people/${personId}/tags`, {
      method: 'DELETE',
      params: { tag },
    });
  }

  // Interactions
  async getPersonTimeline(personId: string, page = 1) {
    return this.fetch<InteractionsListResponse>(`/interactions/person/${personId}/timeline`, {
      params: { page, page_size: 50 },
    });
  }

  async getUpcomingMeetings(days = 7) {
    return this.fetch<{ items: CalendarOccurrence[] }>('/interactions/upcoming', {
      params: { days },
    });
  }

  // Scores
  async listScores(limit = 50) {
    return this.fetch<{ items: PersonScore[]; total: number }>('/scores', {
      params: { limit },
    });
  }

  async getPersonScore(personId: string) {
    return this.fetch<PersonScore>(`/scores/${personId}`);
  }

  async recomputeScores(personId?: string) {
    return this.fetch('/scores/recompute', {
      method: 'POST',
      params: personId ? { person_id: personId } : {},
    });
  }

  // Review Queue
  async getReviewQueue(params: { queue_type?: string; page?: number } = {}) {
    return this.fetch<ReviewQueueResponse>('/review', { params });
  }

  async reviewAction(itemId: string, action: 'accept' | 'reject' | 'ignore') {
    return this.fetch(`/review/${itemId}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  }

  async getReviewStats() {
    return this.fetch('/review/stats');
  }

  // Ingestion
  async getIngestionStatus() {
    return this.fetch('/ingestion/status');
  }

  async ingestLinkedIn() {
    return this.fetch('/ingestion/linkedin', { method: 'POST' });
  }

  async ingestOstCalendar() {
    return this.fetch('/ingestion/ost/calendar', { method: 'POST' });
  }
}

export const api = new APIClient();

// Types
export interface Person {
  id: string;
  full_name: string;
  primary_email: string | null;
  linkedin_url: string | null;
  company: string | null;
  title: string | null;
  tags: string[];
  notes: string | null;
  origin: string;
  is_tracked: boolean;
  linkedin_connected_at: string | null;
  promoted_at: string | null;
  created_at: string;
  updated_at: string;
  emails: { email: string; is_primary: boolean }[];
  score: PersonScore | null;
}

export interface PersonScore {
  person_id: string;
  person_name?: string;
  score_total: number;
  score_breakdown: {
    recency: number;
    recency_max: number;
    recency_reason: string;
    frequency: number;
    frequency_max: number;
    frequency_reason: string;
    bidirectionality: number;
    bidirectionality_max: number;
    bidirectionality_reason: string;
    meetings: number;
    meetings_max: number;
    meetings_reason: string;
    context: number;
    context_max: number;
    context_reason: string;
  };
  interaction_count: number;
  last_interaction_at: string | null;
  next_meeting_at: string | null;
}

export interface PeopleListResponse {
  items: Person[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface Interaction {
  id: string;
  person_id: string | null;
  kind: string;
  occurred_at: string;
  end_at: string | null;
  direction: string | null;
  channel: string;
  subject: string | null;
  snippet: string | null;
  participants: { email: string; name: string; role?: string }[];
  is_automated: boolean;
  is_bulk: boolean;
  is_meaningful: boolean;
  created_at: string;
}

export interface InteractionsListResponse {
  items: Interaction[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface CalendarOccurrence {
  id: string;
  subject: string | null;
  start_at: string;
  end_at: string | null;
  location: string | null;
  organizer_email: string | null;
  participants: { email: string; name: string }[];
  is_cancelled: boolean;
  is_all_day: boolean;
}

export interface ReviewQueueItem {
  id: string;
  queue_type: string;
  person: {
    id: string;
    full_name: string;
    primary_email: string | null;
    company: string | null;
    origin: string;
    is_tracked: boolean;
  };
  suggested_person: {
    id: string;
    full_name: string;
    primary_email: string | null;
    company: string | null;
  } | null;
  confidence_score: number | null;
  match_reason: Record<string, string> | null;
  interaction_count: number;
  status: string;
  created_at: string;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  total: number;
  page: number;
  page_size: number;
}
