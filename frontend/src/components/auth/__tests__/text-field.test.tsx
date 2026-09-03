import { createRef } from 'react';
import { Text, TextInput } from 'react-native';

import { fireEvent, renderWithProviders, screen } from '@/test-utils';

import { TextField } from '../text-field';

describe('<TextField />', () => {
  it('renders the label and an accessible input', () => {
    renderWithProviders(<TextField label="Email" value="" onChangeText={() => {}} />);

    expect(screen.getByText('Email')).toBeOnTheScreen();
    // the input is reachable by its accessibility label (defaults to the label)
    expect(screen.getByLabelText('Email')).toBeInstanceOf(Object);
  });

  it('forwards autoComplete / textContentType / keyboardType to the native input', () => {
    renderWithProviders(
      <TextField
        label="Email"
        value=""
        onChangeText={() => {}}
        autoComplete="email"
        textContentType="emailAddress"
        keyboardType="email-address"
      />,
    );

    const input = screen.getByLabelText('Email');
    expect(input.props.autoComplete).toBe('email');
    expect(input.props.textContentType).toBe('emailAddress');
    expect(input.props.keyboardType).toBe('email-address');
  });

  it('passes an explicit accessibilityHint through and lets accessibilityLabel be overridden', () => {
    renderWithProviders(
      <TextField
        label="Email"
        accessibilityLabel="Work email"
        accessibilityHint="We never share this"
        value=""
        onChangeText={() => {}}
      />,
    );

    const input = screen.getByLabelText('Work email');
    expect(input.props.accessibilityHint).toBe('We never share this');
  });

  it('calls onChangeText when the user types', () => {
    const onChangeText = jest.fn();
    renderWithProviders(<TextField label="Email" value="" onChangeText={onChangeText} />);

    fireEvent.changeText(screen.getByLabelText('Email'), 'a@b.com');
    expect(onChangeText).toHaveBeenCalledWith('a@b.com');
  });

  it('shows the error message as a live-region alert and marks the input invalid', () => {
    renderWithProviders(
      <TextField label="Email" value="x" onChangeText={() => {}} error="Enter a valid email" />,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Enter a valid email');
    expect(alert.props.accessibilityLiveRegion).toBe('polite');

    expect(screen.getByLabelText('Email').props['aria-invalid']).toBe(true);
  });

  it('renders no alert node when there is no error', () => {
    renderWithProviders(<TextField label="Email" value="" onChangeText={() => {}} />);

    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByLabelText('Email').props['aria-invalid']).toBeFalsy();
  });

  it('renders a trailing accessory next to the input', () => {
    renderWithProviders(
      <TextField
        label="Password"
        value=""
        onChangeText={() => {}}
        trailing={<Text>toggle</Text>}
      />,
    );

    expect(screen.getByText('toggle')).toBeOnTheScreen();
  });

  it('forwards secureTextEntry and forwards its ref to the TextInput', () => {
    const ref = createRef<TextInput>();
    renderWithProviders(
      <TextField label="Password" value="" onChangeText={() => {}} secureTextEntry ref={ref} />,
    );

    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
    expect(ref.current).not.toBeNull();
  });
});
