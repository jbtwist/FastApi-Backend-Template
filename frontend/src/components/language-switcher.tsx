/**
 * Language picker: a compact trigger showing the active language, opening a
 * list of every locale the app ships directly beneath it.
 *
 * A list rather than a segmented control because `SUPPORTED_LOCALES` is meant to
 * grow — a row of buttons stops fitting somewhere around the third language,
 * while this stays the same size and scrolls.
 *
 * The list is drawn in a root-level overlay positioned at the trigger's measured
 * screen coordinates, rather than as an absolutely-positioned child of the
 * trigger. Visually the two are identical, but a child would sit inside the auth
 * card's `ScrollView`, where any ancestor's `overflow` or stacking context can
 * clip it or swallow its clicks. The overlay has no ancestors, so it can't be
 * covered, and it gives press-outside-to-dismiss for free.
 *
 * Mounted on web only: a browser's language list is a global setting a visitor
 * won't change for one site, so the app has to offer the choice itself. Native
 * follows the device language, which the user already controls per-app in the
 * OS settings.
 */
import { useCallback, useRef, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { SUPPORTED_LOCALES, LOCALE_LABELS, type Locale } from '@/i18n';
import { FLAG_BY_LOCALE } from '@/i18n/flags';
import { useTranslation } from '@/i18n/provider';

/** Caps the list at roughly six rows before it scrolls. */
const MAX_LIST_HEIGHT = 280;
const MIN_LIST_WIDTH = 200;
const GAP = Spacing.one;
/** Keeps the list off the very edge when the trigger sits in a corner. */
const SCREEN_MARGIN = Spacing.two;

type Anchor = { x: number; y: number; width: number; height: number };

function Flag({ locale, width }: { locale: Locale; width?: number }) {
  const Component = FLAG_BY_LOCALE[locale];
  // Decorative: the language's name next to it is the real label.
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Component width={width} />
    </View>
  );
}

export function LanguageSwitcher() {
  const theme = useTheme();
  const { t, locale, setLocale } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();

  const triggerRef = useRef<View>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  // Both stay untouched on touch devices, which never fire hover.
  const [hovered, setHovered] = useState<Locale | null>(null);
  const [triggerHovered, setTriggerHovered] = useState(false);

  const open = anchor !== null;
  const close = useCallback(() => {
    setAnchor(null);
    // Otherwise the row under the cursor stays lit the next time it opens.
    setHovered(null);
  }, []);

  const toggle = useCallback(() => {
    if (open) {
      close();
      return;
    }
    // Measured on open rather than on layout so the position is right even after
    // the page has scrolled since the trigger was laid out.
    triggerRef.current?.measureInWindow((x, y, width, height) =>
      setAnchor({ x, y, width, height }),
    );
  }, [open, close]);

  const choose = (next: Locale) => {
    close();
    if (next !== locale) void setLocale(next);
  };

  const listWidth = Math.max(MIN_LIST_WIDTH, anchor?.width ?? 0);
  // Right-align with the trigger, then pull back inside the screen if that
  // would overflow — the trigger usually sits near the right edge of a header.
  const left = anchor
    ? Math.max(
        SCREEN_MARGIN,
        Math.min(anchor.x + anchor.width - listWidth, screenWidth - listWidth - SCREEN_MARGIN),
      )
    : 0;

  return (
    <>
      <Pressable
        ref={triggerRef}
        testID="language-switcher"
        accessibilityRole="button"
        accessibilityLabel={t('common.language')}
        accessibilityValue={{ text: LOCALE_LABELS[locale] }}
        accessibilityState={{ expanded: open }}
        onPress={toggle}
        onHoverIn={() => setTriggerHovered(true)}
        onHoverOut={() => setTriggerHovered(false)}
        style={({ pressed }) => [
          styles.trigger,
          { borderColor: theme.border },
          (triggerHovered || open) && { backgroundColor: theme.backgroundElement },
          pressed && { backgroundColor: theme.backgroundSelected },
        ]}>
        <Flag locale={locale} />
        <ThemedText type="small">{LOCALE_LABELS[locale]}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {open ? '▴' : '▾'}
        </ThemedText>
      </Pressable>

      <Modal visible={open} transparent animationType="none" onRequestClose={close}>
        <Pressable
          testID="language-switcher-backdrop"
          accessibilityRole="button"
          accessibilityLabel={t('common.close')}
          style={styles.backdrop}
          onPress={close}
        />
        {anchor ? (
          <View
            testID="language-switcher-list"
            accessibilityRole="radiogroup"
            accessibilityLabel={t('common.language')}
            style={[
              styles.dropdown,
              {
                top: anchor.y + anchor.height + GAP,
                left,
                width: listWidth,
                backgroundColor: theme.background,
                borderColor: theme.border,
              },
            ]}>
            <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
              {SUPPORTED_LOCALES.map((code) => {
                const selected = code === locale;
                return (
                  <Pressable
                    key={code}
                    accessibilityRole="radio"
                    accessibilityLabel={LOCALE_LABELS[code]}
                    accessibilityState={{ checked: selected, selected }}
                    onPress={() => choose(code)}
                    onHoverIn={() => setHovered(code)}
                    onHoverOut={() => setHovered((c) => (c === code ? null : c))}
                    style={({ pressed }) => [
                      styles.row,
                      // Selected outranks hover, so the active row stays legible
                      // as the cursor passes over it; pressing shows through.
                      hovered === code && !selected && { backgroundColor: theme.backgroundElement },
                      (selected || pressed) && { backgroundColor: theme.backgroundSelected },
                    ]}>
                    <Flag locale={code} width={28} />
                    <ThemedText
                      type="small"
                      themeColor={selected ? 'text' : 'textSecondary'}
                      style={styles.rowLabel}>
                      {LOCALE_LABELS[code]}
                    </ThemedText>
                    {selected ? (
                      <ThemedText type="small" themeColor="tint">
                        ✓
                      </ThemedText>
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        ) : null}
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  // Matches `ThemeSwitcher`'s pill so the two read as one group in the header.
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: Spacing.two,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: Spacing.three,
    paddingVertical: Spacing.one + Spacing.half,
    paddingHorizontal: Spacing.two,
    cursor: 'pointer',
  },
  backdrop: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  dropdown: {
    position: 'absolute',
    maxHeight: MAX_LIST_HEIGHT,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: Spacing.two,
    paddingVertical: Spacing.one,
    elevation: 8,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.18)',
  },
  list: { maxHeight: MAX_LIST_HEIGHT },
  listContent: { paddingVertical: Spacing.half },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    cursor: 'pointer',
  },
  rowLabel: { flex: 1 },
});
