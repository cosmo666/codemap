<?php

namespace App;

use App\Util\Strings;

/** Prints the banner. */
function banner(): string
{
    return Strings::upper("codemap");
}

echo banner();
