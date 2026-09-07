import { fireEvent, renderWithProviders, screen } from '@/test-utils';

import { ProviderButtons } from './provider-buttons';

describe('<ProviderButtons />', () => {
  it('renders one button per provider', () => {
    renderWithProviders(<ProviderButtons providers={['google', 'apple']} enabled />);

    expect(screen.getByText('Continue with Google')).toBeOnTheScreen();
    expect(screen.getByText('Continue with Apple')).toBeOnTheScreen();
  });

  it('calls onSelect with the provider and shows no notice when oauth is enabled', () => {
    const onSelect = jest.fn();
    renderWithProviders(
      <ProviderButtons providers={['google']} enabled onSelect={onSelect} />,
    );

    fireEvent.press(screen.getByRole('button', { name: 'Continue with Google' }));

    expect(onSelect).toHaveBeenCalledWith('google');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a "coming soon" notice and starts no flow when oauth is disabled', () => {
    const onSelect = jest.fn();
    renderWithProviders(
      <ProviderButtons providers={['google']} enabled={false} onSelect={onSelect} />,
    );

    const button = screen.getByRole('button', { name: 'Continue with Google' });
    expect(button.props.accessibilityState).toMatchObject({ disabled: true });

    fireEvent.press(button);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Third-party sign-in is coming soon.');
  });

  it('defaults to the app auth config — providers shown, oauth inert', () => {
    const onSelect = jest.fn();
    renderWithProviders(<ProviderButtons onSelect={onSelect} />);

    expect(screen.getByText('Continue with Google')).toBeOnTheScreen();
    expect(screen.getByText('Continue with Apple')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Continue with Apple' }));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Third-party sign-in is coming soon.');
  });

  it('renders nothing when there are no providers', () => {
    renderWithProviders(<ProviderButtons providers={[]} />);

    expect(screen.queryByTestId('provider-buttons')).toBeNull();
  });
});
