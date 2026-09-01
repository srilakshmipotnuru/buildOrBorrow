import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import './CustomSelect.css';

export interface SelectOption {
  label: string;
  value: string;
}

interface CustomSelectProps {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export const CustomSelect: React.FC<CustomSelectProps> = ({
  options,
  value,
  onChange,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedIndex = options.findIndex((opt) => opt.value === value);
  const selectedOption = options[selectedIndex >= 0 ? selectedIndex : 0] || options[0];

  // Sync highlighted index when dropdown opens
  useEffect(() => {
    if (isOpen) {
      setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
    }
  }, [isOpen, selectedIndex]);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (val: string) => {
    onChange(val);
    setIsOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;

    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'Escape':
      case 'Tab':
        setIsOpen(false);
        break;
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev + 1) % options.length);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev - 1 + options.length) % options.length);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (options[highlightedIndex]) {
          handleSelect(options[highlightedIndex].value);
        }
        break;
    }
  };

  return (
    <div
      className={`custom-select-container ${disabled ? 'disabled' : ''}`}
      ref={containerRef}
      onKeyDown={handleKeyDown}
    >
      {/* Select Trigger Button */}
      <button
        type="button"
        className={`select-trigger ${isOpen ? 'open' : ''}`}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label="Select Ecosystem"
      >
        <span className="trigger-label">{selectedOption ? selectedOption.label : 'Select...'}</span>
        <ChevronDown className={`trigger-arrow ${isOpen ? 'rotated' : ''}`} />
      </button>

      {/* Floating Menu Popover */}
      {isOpen && (
        <div className="select-popover">
          <ul
            className="select-options-list"
            role="listbox"
            tabIndex={-1}
            aria-activedescendant={options[highlightedIndex]?.value}
          >
            {options.map((option, idx) => {
              const isSelected = option.value === value;
              const isHighlighted = idx === highlightedIndex;
              return (
                <li
                  key={option.value}
                  id={option.value}
                  role="option"
                  aria-selected={isSelected}
                  className={`select-option-item ${isSelected ? 'selected' : ''} ${
                    isHighlighted ? 'highlighted' : ''
                  }`}
                  onClick={() => handleSelect(option.value)}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                >
                  <span className="option-label">{option.label}</span>
                  {isSelected && <Check className="check-icon" />}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};
