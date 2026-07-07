<?php

namespace App\Util;

/** String helpers. */
class Strings
{
    /** Upper-cases a value. */
    public static function upper(string $value): string
    {
        return strtoupper($value);
    }
}
