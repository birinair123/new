'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Navigation } from '@/components/Navigation';
import { api } from '@/lib/api';

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const { authenticated } = await api.checkAuth();
        if (!authenticated) {
          router.replace('/login');
          return;
        }
      } catch {
        router.replace('/login');
        return;
      }
      setLoading(false);
    };
    checkAuth();
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-600 border-t-transparent mx-auto"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-20">
      {children}
      <Navigation />
    </div>
  );
}
