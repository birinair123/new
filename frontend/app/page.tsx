'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const { authenticated } = await api.checkAuth();
        if (authenticated) {
          router.replace('/people');
        } else {
          router.replace('/login');
        }
      } catch {
        router.replace('/login');
      }
    };
    checkAuth();
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-600 border-t-transparent mx-auto"></div>
        <p className="text-gray-500 mt-4">Loading...</p>
      </div>
    </div>
  );
}
