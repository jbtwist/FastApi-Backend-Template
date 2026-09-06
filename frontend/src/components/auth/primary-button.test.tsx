import { fireEvent, renderWithProviders, screen } from '../../../test-utils';

import { PrimaryButton } from './primary-button';

describe('<PrimaryButton />', () => {
  it('renders the label and fires onPress once', () => {
    const onPress = jest.fn();
    renderWithProviders(<PrimaryButton label="Sign in" onPress={onPress} />);

    fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('shows a spinner instead of the label and swallows taps while submitting', () => {
    const onPress = jest.fn();
    renderWithProviders(<PrimaryButton label="Sign in" onPress={onPress} submitting />);

    expect(screen.getByTestId('primary-button-spinner')).toBeOnTheScreen();
    expect(screen.queryByText('Sign in')).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('swallows taps and shows no spinner while disabled', () => {
    const onPress = jest.fn();
    renderWithProviders(<PrimaryButton label="Sign in" onPress={onPress} disabled />);

    expect(screen.queryByTestId('primary-button-spinner')).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('exposes busy / disabled state to assistive tech', () => {
    renderWithProviders(<PrimaryButton label="Sign in" onPress={() => {}} submitting />);

    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(button.props.accessibilityState).toMatchObject({ disabled: true, busy: true });
  });
});
