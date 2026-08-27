/**
 * 主题上下文
 * 提供主题状态和切换方法
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { ThemeType, ThemeColors, themes } from './colors';

interface ThemeContextType {
  themeType: ThemeType;
  colors: ThemeColors;
  toggleTheme: (event?: React.MouseEvent) => void;
  setTheme: (type: ThemeType) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_STORAGE_KEY = 'tmc-theme';

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [themeType, setThemeType] = useState<ThemeType>(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      return (saved as ThemeType) || 'light';
    } catch {
      return 'light';
    }
  });
  
  const colors = themes[themeType];

  useEffect(() => {
    // 应用主题类到多个元素，确保样式生效
    const elements = [
      document.documentElement,
      document.body,
      document.getElementById('root')
    ].filter(Boolean) as HTMLElement[];
    
    elements.forEach(el => {
      el.classList.remove('theme-light', 'theme-dark');
      el.classList.add(`theme-${themeType}`);
    });
    
    // 同时设置 data-theme 属性（用于CSS变量）
    document.documentElement.setAttribute('data-theme', themeType);
    
    // 保存到 localStorage
    try {
      localStorage.setItem(THEME_STORAGE_KEY, themeType);
    } catch (error) {
      console.warn('无法保存主题配置:', error);
    }
  }, [themeType]);

  const toggleTheme = (event?: React.MouseEvent) => {
    const newTheme = themeType === 'light' ? 'dark' : 'light';
    
    // 使用 View Transitions API 实现平滑过渡
    if (event && 'startViewTransition' in document) {
      const x = event.clientX;
      const y = event.clientY;
      const endRadius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );

      // @ts-ignore
      const transition = document.startViewTransition(() => {
        setThemeType(newTheme);
      });

      transition.ready.then(() => {
        document.documentElement.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${endRadius}px at ${x}px ${y}px)`
            ]
          },
          {
            duration: 300,
            easing: 'cubic-bezier(0.4, 0.0, 0.2, 1)',
            pseudoElement: '::view-transition-new(root)'
          }
        );
      });
    } else {
      setThemeType(newTheme);
    }
  };

  const setTheme = (type: ThemeType) => {
    setThemeType(type);
  };

  return (
    <ThemeContext.Provider value={{ themeType, colors, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useThemeContext = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useThemeContext must be used within ThemeProvider');
  }
  return context;
};
