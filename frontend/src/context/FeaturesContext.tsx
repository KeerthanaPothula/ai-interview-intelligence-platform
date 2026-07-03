import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getHealth } from '../api/client';

interface FeaturesContextValue {
  audioEnabled: boolean;
}

const FeaturesContext = createContext<FeaturesContextValue>({ audioEnabled: true });

export function FeaturesProvider({ children }: { children: ReactNode }) {
  const [audioEnabled, setAudioEnabled] = useState(true);

  useEffect(() => {
    getHealth()
      .then((h) => setAudioEnabled(h.audio_processing_enabled))
      .catch(() => {
        // Network error or backend unreachable — keep the optimistic default
        // so the UI doesn't hide audio controls while the server is starting up.
      });
  }, []);

  return (
    <FeaturesContext.Provider value={{ audioEnabled }}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures(): FeaturesContextValue {
  return useContext(FeaturesContext);
}
