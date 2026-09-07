import { renderWithProviders, screen } from '@/test-utils';

import { FormMessage } from './form-message';

describe('<FormMessage />', () => {
  it('renders nothing when there is no message', () => {
    renderWithProviders(<FormMessage message={null} />);

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders an error message as an alert carrying the text', () => {
    renderWithProviders(
      <FormMessage message={{ kind: 'error', text: 'Email or password is incorrect.' }} />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Email or password is incorrect.');
  });

  it('announces politely for screen readers', () => {
    renderWithProviders(<FormMessage message={{ kind: 'info', text: 'Heads up' }} />);

    expect(screen.getByRole('alert').props.accessibilityLiveRegion).toBe('polite');
  });

  it('swaps its content when the message changes', () => {
    const { rerender } = renderWithProviders(
      <FormMessage message={{ kind: 'success', text: 'Saved' }} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Saved');

    rerender(<FormMessage message={{ kind: 'error', text: 'Nope' }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Nope');
    expect(screen.queryByText('Saved')).toBeNull();
  });
});
