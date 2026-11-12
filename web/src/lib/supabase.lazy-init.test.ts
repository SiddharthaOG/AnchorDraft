import { describe, expect, it, vi } from 'vitest';

describe('Supabase client initialization', () => {
  it('does not require Supabase environment variables just to import app modules', async () => {
    vi.resetModules();
    const getSupabaseClient = vi.fn(() => {
      throw new Error('Supabase environment is not configured');
    });
    vi.doMock('./supabase', () => ({ getSupabaseClient }));

    await expect(import('./data')).resolves.toBeDefined();
    await expect(import('../features/auth/authService')).resolves.toBeDefined();

    expect(getSupabaseClient).not.toHaveBeenCalled();
    vi.doUnmock('./supabase');
  });
});
